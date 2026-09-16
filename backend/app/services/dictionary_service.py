import json
import logging
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import SessionLocal
from app.core.exceptions import AppError, ConflictError, NotFoundError, ValidationAppError
from app.core.query_cache import invalidate as invalidate_query_cache
from app.models.dictionary import DictEntry, Dictionary
from app.parsers.base import DictionaryParser
from app.parsers.ecdict import EcdictParser
from app.parsers.mdict import MDictParser
from app.parsers.stardict import StarDictParser
from app.schemas.dictionary import VALID_FORMATS
from app.services.audit_service import log_action
from app.services.background_task_service import background_tasks

logger = logging.getLogger("mydict.dictionary")

BATCH_SIZE = 2000

_PARSERS: dict[str, type[DictionaryParser]] = {
    "mdict": MDictParser,
    "stardict": StarDictParser,
    "ecdict": EcdictParser,
}

# 上传/目录导入时按声明的 format 做文件后缀白名单校验，防止内容与声明格式不符
# （如把任意文件伪装成词典上传）；具体格式细节仍由各 Parser 在解析阶段兜底校验。
_ALLOWED_EXTENSIONS: dict[str, set[str]] = {
    "mdict": {".mdx", ".mdd"},
    "stardict": {".ifo", ".idx", ".dict", ".syn", ".dict.dz", ".idx.gz"},
    "ecdict": {".csv"},
}


def _validate_file_extensions(format_: str, paths: list[Path]) -> None:
    allowed = _ALLOWED_EXTENSIONS[format_]
    for path in paths:
        name = path.name.lower()
        if not any(name.endswith(ext) for ext in allowed):
            raise ValidationAppError(f"文件 {path.name} 的类型与所选格式「{format_}」不匹配")
    # ECDICT 一个 CSV 就是一部完整词典，选多个会静默只解析第一个（EcdictParser 只读
    # file_paths[0]），选错容易误以为都导入了，这里提前挡住给出明确提示。
    if format_ == "ecdict" and len(paths) != 1:
        raise ValidationAppError("ECDICT 格式只能选择一个 CSV 文件；多个 CSV 请分别单独导入")


def list_dictionaries(db: Session) -> list[Dictionary]:
    return db.query(Dictionary).order_by(Dictionary.sort_order, Dictionary.id).all()


def _imported_dicts_dir_relpaths(db: Session, inbox: Path) -> set[str]:
    """dicts_dir 方式导入时 file_path 存的是原始文件的绝对路径（分号分隔，见
    import_dictionary），换算成相对 /data/dicts 的路径用于比对——支持子目录后不同目录下的
    同名文件不能只按文件名判断是否已导入，否则会互相误标。"""
    rows = db.query(Dictionary.file_path).filter(Dictionary.import_method == "dicts_dir").all()
    relpaths: set[str] = set()
    for (file_path,) in rows:
        if not file_path:
            continue
        for raw in file_path.split(";"):
            raw = raw.strip()
            if not raw:
                continue
            try:
                relpaths.add(Path(raw).resolve().relative_to(inbox).as_posix())
            except ValueError:
                continue
    return relpaths


def _resolve_dicts_subdir(inbox: Path, subpath: str) -> Path:
    """把前端传来的相对路径（如 "sub/dir"）拼到 /data/dicts 下并校验没有越权到目录外。"""
    parts = [p for p in subpath.split("/") if p]
    if any(p in (".", "..") for p in parts):
        raise ValidationAppError(f"非法路径：{subpath}")
    target = (inbox / Path(*parts)).resolve() if parts else inbox
    if target != inbox and inbox not in target.parents:
        raise ValidationAppError(f"非法路径：{subpath}")
    return target


def list_dicts_dir_files(
    db: Session, settings: Settings, subpath: str = ""
) -> tuple[str, list[dict]]:
    inbox = Path(settings.dicts_inbox_path).resolve()
    target = _resolve_dicts_subdir(inbox, subpath)
    normalized = "" if target == inbox else target.relative_to(inbox).as_posix()
    if not target.is_dir():
        return normalized, []

    imported_relpaths = _imported_dicts_dir_relpaths(db, inbox)
    dirs: list[Path] = []
    files: list[Path] = []
    for path in target.iterdir():
        if path.is_dir():
            dirs.append(path)
        elif path.is_file():
            files.append(path)

    entries: list[dict] = []
    for path in sorted(dirs, key=lambda p: p.name.lower()):
        stat = path.stat()
        entries.append(
            {
                "name": path.name,
                "size": 0,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                "imported": False,
                "is_dir": True,
            }
        )
    for path in sorted(files, key=lambda p: p.name.lower()):
        stat = path.stat()
        relpath = path.relative_to(inbox).as_posix()
        entries.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                "imported": relpath in imported_relpaths,
                "is_dir": False,
            }
        )
    return normalized, entries


def resolve_dicts_dir_files(filenames: list[str], settings: Settings) -> list[Path]:
    """白名单校验：只允许引用 /data/dicts 目录（含子目录）下已存在的文件，禁止路径穿越。"""
    inbox = Path(settings.dicts_inbox_path).resolve()
    resolved: list[Path] = []
    for filename in filenames:
        if not filename or filename.startswith("/") or "\\" in filename:
            raise ValidationAppError(f"非法文件名：{filename}")
        parts = [p for p in filename.split("/") if p]
        if not parts or any(p in (".", "..") for p in parts):
            raise ValidationAppError(f"非法文件名：{filename}")
        candidate = (inbox / Path(*parts)).resolve()
        if (candidate != inbox and inbox not in candidate.parents) or not candidate.is_file():
            raise ValidationAppError(f"文件不存在于待导入目录：{filename}")
        resolved.append(candidate)
    return resolved


def _validate_format(format_: str) -> None:
    if format_ not in VALID_FORMATS:
        raise ValidationAppError(f"不支持的词典格式：{format_}")


def start_dictionary_import(
    *,
    name: str,
    format_: str,
    lang_from: str,
    lang_to: str,
    staged_paths: list[Path],
    settings: Settings,
    admin_id: int,
    import_method: str,
) -> int:
    """校验参数后把解析入库丢进后台线程，立即返回任务 id 供前端轮询。

    格式/文件名校验很快，留在调用方所在的请求线程里同步做，坏输入能在提交的当次
    请求就报错；真正耗时的解析、批量入库放到后台线程，避免大词典（几十万词条）
    导入时占住请求几分钟——之前整个导入都同步跑在请求里，前端 axios 10 秒超时会
    先一步掐断请求（虽然后端还在继续跑、最终会导入成功），界面上看起来像"导入
    没反应"，词典其实要再等一段时间才能查到。
    """
    _validate_format(format_)
    _validate_file_extensions(format_, staged_paths)

    task = background_tasks.start("dictionary_import", name)
    thread = threading.Thread(
        target=_run_import_in_background,
        args=(
            task.id,
            name,
            format_,
            lang_from,
            lang_to,
            staged_paths,
            settings,
            admin_id,
            import_method,
        ),
        daemon=True,
    )
    thread.start()
    return task.id


def _run_import_in_background(
    task_id: int,
    name: str,
    format_: str,
    lang_from: str,
    lang_to: str,
    staged_paths: list[Path],
    settings: Settings,
    admin_id: int,
    import_method: str,
) -> None:
    """后台线程入口：请求生命周期已经结束，不能沿用请求的 db session，这里单独开一个。"""
    db = SessionLocal()
    try:
        dictionary = import_dictionary(
            db,
            task_id=task_id,
            name=name,
            format_=format_,
            lang_from=lang_from,
            lang_to=lang_to,
            staged_paths=staged_paths,
            settings=settings,
            admin_id=admin_id,
            import_method=import_method,
        )
        background_tasks.succeed(
            task_id, {"dictionary_id": dictionary.id, "word_count": dictionary.word_count}
        )
    except AppError as exc:
        background_tasks.fail(task_id, exc.message)
    except Exception:
        logger.exception("词典导入后台任务失败：%s", name)
        background_tasks.fail(task_id, "导入失败：服务器内部错误，请查看后端日志")
    finally:
        db.close()


def import_dictionary(
    db: Session,
    *,
    task_id: int,
    name: str,
    format_: str,
    lang_from: str,
    lang_to: str,
    staged_paths: list[Path],
    settings: Settings,
    admin_id: int,
    import_method: str,
) -> Dictionary:
    """解析并导入词典。调用方需已完成格式/文件名校验并登记好 task_id（见
    start_dictionary_import），这里只管解析入库、更新任务进度。

    import_method="upload"：staged_paths 是浏览器上传的暂存文件，成功后移动归档到该词典的
    source/ 目录，由本应用管理，删除词典时一并清理。
    import_method="dicts_dir"：staged_paths 是用户自己放进 /data/dicts 的文件，不移动、不
    归档、不在删除词典时代为清理——目录是用户自己管的，删不删由用户自己决定。

    失败时清理已写入的 dict_entries/资源文件/词典记录，staged_paths 保留在原处（便于重试）。
    """
    dictionary = Dictionary(
        name=name,
        format=format_,
        lang_from=lang_from,
        lang_to=lang_to,
        file_path="",
        status="disabled",
        imported_by=admin_id,
        import_method=import_method,
    )
    db.add(dictionary)
    db.flush()  # 拿到自增 id，供资源目录与 HTML 改写使用

    dict_id = dictionary.id
    storage_root = Path(settings.dictionary_storage_path) / str(dict_id)
    resource_dir = storage_root / "res"
    source_dir = storage_root / "source"

    try:
        parser = _PARSERS[format_]()
        word_count = _batch_insert(
            db,
            dict_id,
            parser.parse(staged_paths, dictionary_id=dict_id, resource_dir=resource_dir),
            on_progress=lambda done: background_tasks.update_progress(task_id, {"done": done}),
        )

        if import_method == "upload":
            source_dir.mkdir(parents=True, exist_ok=True)
            for path in staged_paths:
                shutil.move(str(path), str(source_dir / path.name))
            dictionary.file_path = str(source_dir)
        else:
            dictionary.file_path = "; ".join(str(p) for p in staged_paths)

        dictionary.word_count = word_count
        db.commit()
    except Exception as exc:
        # dict_id 所在的行/词条从未提交过，rollback 即可完整撤销数据库侧改动；
        # 只需额外清理已落盘的资源目录（不受事务管理）。
        db.rollback()
        if storage_root.exists():
            shutil.rmtree(storage_root, ignore_errors=True)
        # 解析器对文件内容/完整性的校验以 ValueError 表达，统一转成业务校验错误而非
        # 未预期的内部错误，让管理员看到具体原因（如缺少必要文件）。
        if isinstance(exc, ValueError):
            raise ValidationAppError(str(exc)) from exc
        raise

    log_action(
        db,
        actor_type="admin",
        actor_id=admin_id,
        action="dictionary.import",
        target=str(dict_id),
        detail={"name": name, "format": format_, "word_count": dictionary.word_count},
    )
    invalidate_query_cache()
    db.refresh(dictionary)
    return dictionary


def _batch_insert(db: Session, dictionary_id: int, entries, on_progress=None) -> int:
    count = 0
    batch: list[DictEntry] = []
    seen_words: set[str] = set()
    for entry in entries:
        if entry.word in seen_words:
            continue  # UNIQUE(dictionary_id, word)：同名词条（如 StarDict 别名冲突）仅保留首条
        seen_words.add(entry.word)
        batch.append(
            DictEntry(
                dictionary_id=dictionary_id,
                word=entry.word,
                word_lower=entry.word.lower(),
                phonetic=entry.phonetic,
                definition=entry.definition,
                extra=json.dumps(entry.extra, ensure_ascii=False) if entry.extra else None,
            )
        )
        count += 1
        if len(batch) >= BATCH_SIZE:
            db.bulk_save_objects(batch)
            db.flush()
            batch.clear()
            if on_progress:
                on_progress(count)
    if batch:
        db.bulk_save_objects(batch)
        db.flush()
    if on_progress:
        on_progress(count)
    return count


def set_dictionary_status(
    db: Session, dictionary_id: int, status: str, admin_id: int
) -> Dictionary:
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise NotFoundError("词典不存在")
    dictionary.status = status
    db.commit()
    log_action(
        db,
        actor_type="admin",
        actor_id=admin_id,
        action=f"dictionary.{status}",
        target=str(dictionary_id),
    )
    invalidate_query_cache()
    db.refresh(dictionary)
    return dictionary


def update_dictionary_metadata(
    db: Session, dictionary_id: int, name: str, lang_from: str, lang_to: str, admin_id: int
) -> Dictionary:
    """只改名称/语言方向，不涉及重新解析——已入库的词条内容不受影响。"""
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise NotFoundError("词典不存在")
    dictionary.name = name
    dictionary.lang_from = lang_from
    dictionary.lang_to = lang_to
    db.commit()
    log_action(
        db,
        actor_type="admin",
        actor_id=admin_id,
        action="dictionary.update",
        target=str(dictionary_id),
        detail={"name": name, "lang_from": lang_from, "lang_to": lang_to},
    )
    # lang_from/lang_to 会影响 resolve_dictionaries 的语言路由匹配，缓存的查询结果里
    # 也带着词典名称快照，改名/改语言方向后都要让缓存失效
    invalidate_query_cache()
    db.refresh(dictionary)
    return dictionary


def delete_dictionary(db: Session, dictionary_id: int, admin_id: int, settings: Settings) -> None:
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise NotFoundError("词典不存在")
    import_method = dictionary.import_method
    db.delete(dictionary)  # dict_entries 由外键 ON DELETE CASCADE 一并删除，见 db.py 的 FK pragma
    db.commit()
    log_action(
        db,
        actor_type="admin",
        actor_id=admin_id,
        action="dictionary.delete",
        target=str(dictionary_id),
    )

    # res/ 是解析时提取的图片/音频等派生资源，与导入方式无关，直接清理；
    # source/ 只有 upload 方式才是本应用暂存归档的文件，dicts_dir 方式源文件是用户自己放进
    # /data/dicts 的，不属于本应用管理，删不删由用户自己决定，这里不碰。
    storage_root = Path(settings.dictionary_storage_path) / str(dictionary_id)
    resource_dir = storage_root / "res"
    if resource_dir.exists():
        shutil.rmtree(resource_dir, ignore_errors=True)
    if import_method == "upload":
        source_dir = storage_root / "source"
        if source_dir.exists():
            shutil.rmtree(source_dir, ignore_errors=True)
    if storage_root.exists() and not any(storage_root.iterdir()):
        storage_root.rmdir()

    invalidate_query_cache()
    # VACUUM 要重写整个数据库文件，库越大越慢（实测 200MB 库跑到 40+ 秒），同步跑在
    # 删除请求里会让前端 10 秒超时误以为删除没生效（其实后端还在继续跑、最终会删成功，
    # 只是响应没能在超时前返回）；丢到后台线程异步执行，删除接口本身只做行删除和文件
    # 清理，立刻返回。
    threading.Thread(target=_vacuum, args=(db.get_bind(),), daemon=True).start()


def _vacuum(engine) -> None:
    """回收删除词条后 SQLite 文件里的空闲页；VACUUM 不能在事务内跑，用独立的
    autocommit 连接执行。WAL 模式下 VACUUM 本身不会把文件截断到实际大小（新内容通过
    WAL 写入，磁盘上的文件长度要等 checkpoint 才会收缩），额外执行一次 TRUNCATE 模式
    的 checkpoint 才能让文件大小真正降下来。"""
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("VACUUM"))
            conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
    except Exception:
        logger.exception("VACUUM 失败，不影响词典已经删除成功，磁盘空间下次删除词典时会重试回收")


def reorder_dictionaries(db: Session, ordered_ids: list[int], admin_id: int) -> list[Dictionary]:
    dictionaries = {
        d.id: d for d in db.query(Dictionary).filter(Dictionary.id.in_(ordered_ids)).all()
    }
    if len(dictionaries) != len(set(ordered_ids)):
        raise ConflictError("排序列表包含不存在的词典 ID")
    for index, dict_id in enumerate(ordered_ids):
        dictionaries[dict_id].sort_order = index
    db.commit()
    log_action(
        db,
        actor_type="admin",
        actor_id=admin_id,
        action="dictionary.reorder",
        detail={"order": ordered_ids},
    )
    return list_dictionaries(db)


def test_query(db: Session, dictionary_id: int, word: str, limit: int = 20) -> list[DictEntry]:
    if db.get(Dictionary, dictionary_id) is None:
        raise NotFoundError("词典不存在")
    word_lower = word.strip().lower()
    return (
        db.query(DictEntry)
        .filter(
            DictEntry.dictionary_id == dictionary_id, DictEntry.word_lower.like(f"{word_lower}%")
        )
        .order_by(DictEntry.word_lower)
        .limit(limit)
        .all()
    )
