import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.core.query_cache import invalidate as invalidate_query_cache
from app.models.dictionary import DictEntry, Dictionary
from app.parsers.base import DictionaryParser
from app.parsers.ecdict import EcdictParser
from app.parsers.mdict import MDictParser
from app.parsers.stardict import StarDictParser
from app.schemas.dictionary import VALID_FORMATS
from app.services.audit_service import log_action
from app.services.background_task_service import background_tasks

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


def list_dictionaries(db: Session) -> list[Dictionary]:
    return db.query(Dictionary).order_by(Dictionary.sort_order, Dictionary.id).all()


def list_dicts_dir_files(settings: Settings) -> list[dict]:
    inbox = Path(settings.dicts_inbox_path)
    if not inbox.exists():
        return []
    files = []
    for path in sorted(inbox.iterdir()):
        if not path.is_file():
            continue
        stat = path.stat()
        files.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            }
        )
    return files


def resolve_dicts_dir_files(filenames: list[str], settings: Settings) -> list[Path]:
    """白名单校验：只允许引用 /data/dicts 目录下已存在的文件，禁止路径穿越。"""
    inbox = Path(settings.dicts_inbox_path).resolve()
    resolved: list[Path] = []
    for filename in filenames:
        if not filename or "/" in filename or "\\" in filename or filename in (".", ".."):
            raise ValidationAppError(f"非法文件名：{filename}")
        candidate = (inbox / filename).resolve()
        if candidate.parent != inbox or not candidate.is_file():
            raise ValidationAppError(f"文件不存在于待导入目录：{filename}")
        resolved.append(candidate)
    return resolved


def _validate_format(format_: str) -> None:
    if format_ not in VALID_FORMATS:
        raise ValidationAppError(f"不支持的词典格式：{format_}")


def import_dictionary(
    db: Session,
    *,
    name: str,
    format_: str,
    lang_from: str,
    lang_to: str,
    staged_paths: list[Path],
    settings: Settings,
    admin_id: int,
    move_source: bool = True,
) -> Dictionary:
    """解析并导入词典；成功后把 staged_paths 移动到该词典的 source/ 归档目录。

    失败时清理已写入的 dict_entries/资源文件/词典记录，staged_paths 保留在原处（便于重试）。
    """
    _validate_format(format_)
    _validate_file_extensions(format_, staged_paths)

    dictionary = Dictionary(
        name=name,
        format=format_,
        lang_from=lang_from,
        lang_to=lang_to,
        file_path="",
        status="disabled",
        imported_by=admin_id,
    )
    db.add(dictionary)
    db.flush()  # 拿到自增 id，供资源目录与 HTML 改写使用

    dict_id = dictionary.id
    storage_root = Path(settings.dictionary_storage_path) / str(dict_id)
    resource_dir = storage_root / "res"
    source_dir = storage_root / "source"

    # 导入过程全程同步跑在这一次请求里（大文件可能耗时较久），这里登记一个后台任务，
    # 让别的标签页/会话打开管理后台时也能看到"正在导入"的状态，见 background_task_service.py。
    task = background_tasks.start("dictionary_import", name)
    try:
        parser = _PARSERS[format_]()
        word_count = _batch_insert(
            db,
            dict_id,
            parser.parse(staged_paths, dictionary_id=dict_id, resource_dir=resource_dir),
            on_progress=lambda done: background_tasks.update_progress(task.id, {"done": done}),
        )

        source_dir.mkdir(parents=True, exist_ok=True)
        if move_source:
            for path in staged_paths:
                shutil.move(str(path), str(source_dir / path.name))

        dictionary.word_count = word_count
        dictionary.file_path = str(source_dir)
        db.commit()
    except Exception as exc:
        # dict_id 所在的行/词条从未提交过，rollback 即可完整撤销数据库侧改动；
        # 只需额外清理已落盘的资源目录（不受事务管理）。
        db.rollback()
        if storage_root.exists():
            shutil.rmtree(storage_root, ignore_errors=True)
        # 解析器对文件内容/完整性的校验以 ValueError 表达，统一转成 4xx 而非 500，
        # 让管理员看到具体原因（如缺少必要文件）；其余异常视为未预期的内部错误照常抛出。
        if isinstance(exc, ValueError):
            raise ValidationAppError(str(exc)) from exc
        raise
    finally:
        background_tasks.finish(task.id)

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


def delete_dictionary(db: Session, dictionary_id: int, admin_id: int, settings: Settings) -> None:
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise NotFoundError("词典不存在")
    db.delete(dictionary)
    db.commit()
    log_action(
        db,
        actor_type="admin",
        actor_id=admin_id,
        action="dictionary.delete",
        target=str(dictionary_id),
    )

    storage_root = Path(settings.dictionary_storage_path) / str(dictionary_id)
    if storage_root.exists():
        shutil.rmtree(storage_root, ignore_errors=True)
    invalidate_query_cache()


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
