import json
import logging
import re
import shutil
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import SessionLocal
from app.core.exceptions import AppError, ConflictError, NotFoundError, ValidationAppError
from app.core.query_cache import invalidate as invalidate_query_cache
from app.models.audit import AuditLog
from app.models.dictionary import DictEntry, Dictionary
from app.parsers.base import DictionaryParser
from app.parsers.ecdict import EcdictParser
from app.parsers.mdict import MDictParser
from app.parsers.stardict import StarDictParser, parse_ifo
from app.schemas.dictionary import VALID_FORMATS
from app.services.audit_service import log_action
from app.services.background_task_service import background_tasks
from app.services.language_detect import detect_language

logger = logging.getLogger("mydict.dictionary")

BATCH_SIZE = 2000

# 语言识别采样条数。词头能做到跨整部词典均匀取样（MDict 的词头表在打开时就已全部读入
# 内存，按下标取值是纯内存操作），所以多取一些几乎不花钱；释义只能顺序多读再过滤，
# 取 200 条足够判断文字种类，再多只是浪费解析时间。
_SAMPLE_HEADWORD_LIMIT = 500
_SAMPLE_DEFINITION_LIMIT = 200

# 识别不出语言时的兜底方向，与前端导入弹窗默认值一致
_FALLBACK_LANG_FROM = "en"
_FALLBACK_LANG_TO = "zh-Hans"

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


# 文件名后缀 → 词典格式
_FORMAT_BY_EXT: dict[str, str] = {
    "mdx": "mdict",
    "mdd": "mdict",
    "ifo": "stardict",
    "idx": "stardict",
    "dict": "stardict",
    "syn": "stardict",
    "idx.gz": "stardict",
    "dict.dz": "stardict",
    "csv": "ecdict",
}

# 一部词典的必需文件：外层是「与」、内层是「或」（.mdd/.syn 可选，不计入）
_REQUIRED_EXTENSIONS: dict[str, tuple[tuple[str, ...], ...]] = {
    "mdict": (("mdx",),),
    "stardict": (("ifo",), ("idx", "idx.gz"), ("dict", "dict.dz")),
    "ecdict": (("csv",),),
}

# 双后缀须先于单后缀匹配
_DOUBLE_EXTENSIONS = ("dict.dz", "idx.gz")

# 入口文件：词典名称与主干以它为准
_ENTRY_EXTENSIONS = {"mdx", "ifo", "csv"}

# MDict 资源分卷 X.1.mdd / X.2.mdd…；X.1 也可能是词典名本身，仅在能对上同目录 .mdx 主干时才剥卷号
_VOLUME_SUFFIX_RE = re.compile(r"\.\d+$")

# 递归扫描的最大深度（相对扫描起点）
_MAX_SCAN_DEPTH = 4


def _split_dict_filename(filename: str) -> tuple[str, str, str] | None:
    """把文件名拆成 (格式, 分组键, 规范后缀)；后缀不属于任何词典格式时返回 None。

    分组键带格式前缀且统一小写，foo.mdx 与 foo.ifo 不会被并成一组。
    """
    lowered = filename.lower()
    for ext in _DOUBLE_EXTENSIONS:
        if lowered.endswith("." + ext):
            stem = filename[: -(len(ext) + 1)]
            format_ = _FORMAT_BY_EXT[ext]
            return (format_, f"{format_}:{stem.lower()}", ext) if stem else None
    ext = lowered.rsplit(".", 1)[-1] if "." in lowered else ""
    format_ = _FORMAT_BY_EXT.get(ext)
    if format_ is None:
        return None
    stem = filename[: -(len(ext) + 1)]
    return (format_, f"{format_}:{stem.lower()}", ext) if stem else None


def _missing_requirements(format_: str, exts: set[str]) -> list[str]:
    """列出该分组还缺哪些必需文件，用来解释为什么不能导入。"""
    return [
        " 或 ".join(f".{ext}" for ext in alternatives)
        for alternatives in _REQUIRED_EXTENSIONS[format_]
        if not any(ext in exts for ext in alternatives)
    ]


def _sanitize_dict_name(raw: str, fallback: str) -> str:
    name = " ".join(raw.split())
    # 与 ImportFromDictsDirRequest.name 的 max_length 对齐
    return (name or fallback)[:255]


def _suggest_dict_name(format_: str, stem: str, paths: list[Path]) -> str:
    """给出建议的词典名称：StarDict 的 .ifo 里有 bookname 字段，其余用文件名主干。"""
    if format_ == "stardict":
        ifo = next((p for p in paths if p.name.lower().endswith(".ifo")), None)
        if ifo is not None:
            try:
                return _sanitize_dict_name(parse_ifo(ifo).get("bookname") or stem, stem)
            except OSError:
                pass
    return _sanitize_dict_name(stem, stem)


def _build_dict_groups(
    files: list[Path], inbox: Path, imported_relpaths: set[str]
) -> tuple[list[dict], list[str]]:
    """把同一目录下的文件按 (格式, 主干) 归组成待导入的词典单元，并列出被忽略的文件。

    多卷 .mdd 仅在同目录存在对应 .mdx 时并组，孤立的 .mdd 单独成组并标缺件。
    """
    mdx_stems = {
        path.name[: -len(".mdx")].lower() for path in files if path.name.lower().endswith(".mdx")
    }

    grouped: dict[str, dict] = {}
    skipped: list[str] = []
    for path in sorted(files, key=lambda p: p.name.lower()):
        split = _split_dict_filename(path.name)
        if split is None:
            skipped.append(path.relative_to(inbox).as_posix())
            continue
        format_, key, ext = split
        if format_ == "mdict" and ext == "mdd":
            stem = path.name[: -(len(ext) + 1)]
            base = _VOLUME_SUFFIX_RE.sub("", stem)
            if base != stem and base.lower() in mdx_stems:
                key = f"mdict:{base.lower()}"
        group = grouped.setdefault(
            key, {"format": format_, "stem": None, "paths": [], "exts": set()}
        )
        group["paths"].append(path)
        group["exts"].add(ext)
        # 主干取入口文件名，避免分卷的「X.1」被当成词典名
        if group["stem"] is None or ext in _ENTRY_EXTENSIONS:
            group["stem"] = path.name[: -(len(ext) + 1)]

    dictionaries: list[dict] = []
    for key, group in grouped.items():
        group_files: list[Path] = sorted(group["paths"], key=lambda p: p.name.lower())
        files_out = []
        for path in group_files:
            relpath = path.relative_to(inbox).as_posix()
            files_out.append(
                {
                    "name": path.name,
                    "relpath": relpath,
                    "size": _file_size(path),
                    "imported": relpath in imported_relpaths,
                }
            )
        missing = _missing_requirements(group["format"], group["exts"])
        dictionaries.append(
            {
                "key": key,
                "name": _suggest_dict_name(group["format"], group["stem"], group_files),
                "format": group["format"],
                "files": files_out,
                "total_size": sum(f["size"] for f in files_out),
                "importable": not missing,
                "reason": f"缺少 {'、'.join(missing)} 文件" if missing else None,
                # 组内文件全部被消费过才算已导入
                "imported": all(f["imported"] for f in files_out),
            }
        )
    dictionaries.sort(key=lambda d: d["name"].lower())
    return dictionaries, sorted(skipped)


def _safe_iterdir(path: Path) -> list[Path]:
    """列目录；无权限或目录中途消失时记 warning 并当作空目录，不让一个坏目录拖垮整次扫描。"""
    try:
        return list(path.iterdir())
    except OSError:
        logger.warning("无法读取目录 %s，已跳过", path, exc_info=True)
        return []


def _mtime(path: Path) -> datetime:
    try:
        timestamp = path.stat().st_mtime
    except OSError:
        timestamp = 0
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _iter_scan_dirs(root: Path, max_depth: int) -> Iterator[Path]:
    """深度受限地遍历 root 及其子目录；跳过以 . 开头的目录与符号链接目录。"""
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        yield current
        if depth >= max_depth:
            continue
        for child in sorted(_safe_iterdir(current), key=lambda p: p.name.lower()):
            if child.is_dir() and not child.is_symlink() and not child.name.startswith("."):
                stack.append((child, depth + 1))


def _build_dict_groups_recursive(
    root: Path, inbox: Path, imported_relpaths: set[str]
) -> tuple[list[dict], list[str]]:
    """逐层扫描 root 下的所有目录，每个目录的文件各自归组，避免不同目录的同名文件互相干扰。"""
    dictionaries: list[dict] = []
    skipped: list[str] = []
    for current in _iter_scan_dirs(root, _MAX_SCAN_DEPTH):
        files = sorted(
            (p for p in _safe_iterdir(current) if p.is_file()), key=lambda p: p.name.lower()
        )
        if not files:
            continue
        groups, ignored = _build_dict_groups(files, inbox, imported_relpaths)
        # 扫描起点之外、且目录里恰好只有一部可导入词典时，用目录名（通常比文件名主干可读）
        importable = [group for group in groups if group["importable"]]
        if current != root and len(importable) == 1:
            importable[0]["name"] = _sanitize_dict_name(current.name, importable[0]["name"])
        for group in groups:
            group["dir"] = current.relative_to(inbox).as_posix() if current != inbox else ""
            dictionaries.append(group)
        skipped.extend(ignored)
    dictionaries.sort(key=lambda d: (d["dir"], d["name"].lower()))
    return dictionaries, sorted(skipped)


def list_dicts_dir_files(
    db: Session, settings: Settings, subpath: str = "", recursive: bool = False
) -> tuple[str, list[dict], list[dict], list[str]]:
    inbox = Path(settings.dicts_inbox_path).resolve()
    target = _resolve_dicts_subdir(inbox, subpath)
    normalized = "" if target == inbox else target.relative_to(inbox).as_posix()
    if not target.is_dir():
        return normalized, [], [], []

    imported_relpaths = _imported_dicts_dir_relpaths(db, inbox)
    dirs: list[Path] = []
    files: list[Path] = []
    for path in _safe_iterdir(target):
        if path.is_dir():
            dirs.append(path)
        elif path.is_file():
            files.append(path)

    entries: list[dict] = []
    for path in sorted(dirs, key=lambda p: p.name.lower()):
        entries.append(
            {
                "name": path.name,
                "size": 0,
                "modified_at": _mtime(path),
                "imported": False,
                "is_dir": True,
            }
        )
    for path in sorted(files, key=lambda p: p.name.lower()):
        relpath = path.relative_to(inbox).as_posix()
        entries.append(
            {
                "name": path.name,
                "size": _file_size(path),
                "modified_at": _mtime(path),
                "imported": relpath in imported_relpaths,
                "is_dir": False,
            }
        )
    if recursive:
        dictionaries, skipped = _build_dict_groups_recursive(target, inbox, imported_relpaths)
    else:
        dictionaries, skipped = _build_dict_groups(files, inbox, imported_relpaths)
        for group in dictionaries:
            group["dir"] = normalized
    return normalized, entries, dictionaries, skipped


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
    lang_from: str | None,
    lang_to: str | None,
    staged_paths: list[Path],
    settings: Settings,
    admin_id: int,
    import_method: str,
    skip_resources: bool = False,
) -> int:
    """校验参数后把解析入库丢进后台线程，立即返回任务 id 供前端轮询。

    格式/文件名校验很快，留在调用方所在的请求线程里同步做，坏输入能在提交的当次
    请求就报错；真正耗时的解析、批量入库放到后台线程，避免大词典（几十万词条）
    导入时占住请求几分钟——之前整个导入都同步跑在请求里，前端 axios 10 秒超时会
    先一步掐断请求（虽然后端还在继续跑、最终会导入成功），界面上看起来像"导入
    没反应"，词典其实要再等一段时间才能查到。

    lang_from/lang_to 传 None 表示导入时自动识别（在后台线程里做）。
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
            skip_resources,
        ),
        daemon=True,
    )
    thread.start()
    return task.id


def _run_import_in_background(
    task_id: int,
    name: str,
    format_: str,
    lang_from: str | None,
    lang_to: str | None,
    staged_paths: list[Path],
    settings: Settings,
    admin_id: int,
    import_method: str,
    skip_resources: bool,
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
            skip_resources=skip_resources,
        )
        background_tasks.succeed(
            task_id,
            {
                "dictionary_id": dictionary.id,
                "word_count": dictionary.word_count,
                "lang_from": dictionary.lang_from,
                "lang_to": dictionary.lang_to,
            },
        )
    except AppError as exc:
        background_tasks.fail(task_id, exc.message)
    except Exception:
        logger.exception("词典导入后台任务失败：%s", name)
        background_tasks.fail(task_id, "导入失败：服务器内部错误，请查看后端日志")
    finally:
        db.close()


def _resolve_languages(
    parser: DictionaryParser,
    staged_paths: list[Path],
    lang_from: str | None,
    lang_to: str | None,
) -> tuple[str, str]:
    """把为 None 的一侧用采样识别出的语言补齐；识别不出时回落到默认方向（列为 NOT NULL）。"""
    if lang_from is not None and lang_to is not None:
        return lang_from, lang_to
    try:
        detected_from, detected_to = detect_language(
            parser.sample_headwords(staged_paths, _SAMPLE_HEADWORD_LIMIT),
            [entry.definition for entry in parser.sample(staged_paths, _SAMPLE_DEFINITION_LIMIT)],
        )
    except Exception:
        # 采样失败不该连累整次导入，回落默认方向，导入后可手动改
        logger.warning("语言方向自动识别失败，回落到默认值", exc_info=True)
        detected_from = detected_to = None
    return (
        lang_from or detected_from or _FALLBACK_LANG_FROM,
        lang_to or detected_to or _FALLBACK_LANG_TO,
    )


def import_dictionary(
    db: Session,
    *,
    task_id: int,
    name: str,
    format_: str,
    lang_from: str | None,
    lang_to: str | None,
    staged_paths: list[Path],
    settings: Settings,
    admin_id: int,
    import_method: str,
    skip_resources: bool = False,
) -> Dictionary:
    """解析并导入词典。调用方需已完成格式/文件名校验并登记好 task_id（见
    start_dictionary_import），这里只管解析入库、更新任务进度。

    lang_from/lang_to 为 None 时按采样结果自动识别；skip_resources=True 时不解包 .mdd 资源。

    import_method="upload"：staged_paths 是浏览器上传的暂存文件，成功后移动归档到该词典的
    source/ 目录，由本应用管理，删除词典时一并清理。
    import_method="dicts_dir"：staged_paths 是用户自己放进 /data/dicts 的文件，不移动、不
    归档、不在删除词典时代为清理——目录是用户自己管的，删不删由用户自己决定。

    失败时清理已写入的 dict_entries/资源文件/词典记录，staged_paths 保留在原处（便于重试）。
    """
    parser = _PARSERS[format_]()
    lang_from, lang_to = _resolve_languages(parser, staged_paths, lang_from, lang_to)

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
    # 不要资源时不建 res/ 目录
    resource_dir = None if skip_resources else storage_root / "res"
    source_dir = storage_root / "source"

    try:
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
        detail={
            "name": name,
            "format": format_,
            "word_count": dictionary.word_count,
            "lang_from": dictionary.lang_from,
            "lang_to": dictionary.lang_to,
            "skip_resources": skip_resources,
        },
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


def source_paths_for(dictionary: Dictionary) -> list[Path]:
    """取回重新解析这部词典所需的源文件路径。

    两种导入方式的 `file_path` 语义不同：dicts_dir 存的是源文件绝对路径（分号分隔），
    upload 存的是归档目录（文件被移进该目录，无扩展名区分，直接取目录内全部文件）。
    """
    raw = (dictionary.file_path or "").strip()
    if not raw:
        return []
    if dictionary.import_method == "upload":
        source_dir = Path(raw)
        if not source_dir.is_dir():
            return []
        return sorted(path for path in source_dir.iterdir() if path.is_file())
    paths: list[Path] = []
    for part in raw.split(";"):
        part = part.strip()
        if part and Path(part).is_file():
            paths.append(Path(part))
    return paths


def detect_dictionary_language(dictionary: Dictionary) -> tuple[str | None, str | None]:
    """按当前采样逻辑重新识别一部词典的语言方向。

    只读源文件，不写库——调用方决定是否落库（见 apply_detected_language）。
    """
    paths = source_paths_for(dictionary)
    if not paths:
        raise ValidationAppError(f"找不到「{dictionary.name}」的源文件，无法重新识别")
    parser = _PARSERS[dictionary.format]()
    headwords = parser.sample_headwords(paths, _SAMPLE_HEADWORD_LIMIT)
    definitions = [entry.definition for entry in parser.sample(paths, _SAMPLE_DEFINITION_LIMIT)]
    return detect_language(headwords, definitions)


def apply_detected_language(
    db: Session, dictionary: Dictionary, detected_from: str | None, detected_to: str | None
) -> bool:
    """把重新识别出的语言方向写回；只覆盖**识别出结论**的那一侧，返回是否有改动。"""
    changed = False
    if detected_from and dictionary.lang_from != detected_from:
        dictionary.lang_from = detected_from
        changed = True
    if detected_to and dictionary.lang_to != detected_to:
        dictionary.lang_to = detected_to
        changed = True
    if changed:
        db.commit()
        # lang_from 直接决定查询路由，缓存里带的是词典名的查询结果快照，必须整体失效
        invalidate_query_cache()
    return changed


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


def set_dictionaries_status(
    db: Session, dictionary_ids: list[int], status: str, admin_id: int
) -> list[Dictionary]:
    """批量启用/停用：状态变更与逐部审计日志在同一事务里提交，任何一步失败都整批回滚。

    重复 ID 去重；只要有一个 ID 不存在就整批拒绝（404）。
    """
    unique_ids = list(dict.fromkeys(dictionary_ids))
    found = {d.id: d for d in db.query(Dictionary).filter(Dictionary.id.in_(unique_ids)).all()}
    missing = [dict_id for dict_id in unique_ids if dict_id not in found]
    if missing:
        raise NotFoundError(f"包含不存在的词典 ID：{missing}")

    try:
        for dict_id in unique_ids:
            found[dict_id].status = status
            db.add(
                AuditLog(
                    actor_type="admin",
                    actor_id=admin_id,
                    action=f"dictionary.{status}",
                    target=str(dict_id),
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    invalidate_query_cache()
    return [found[dict_id] for dict_id in unique_ids]


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
