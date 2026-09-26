import json
import logging
import re
import shutil
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import SessionLocal
from app.core.exceptions import AppError, ConflictError, NotFoundError, ValidationAppError
from app.core.query_cache import invalidate as invalidate_query_cache
from app.models.audit import AuditLog
from app.models.dictionary import DictEntry, Dictionary
from app.parsers.base import DictionaryParser
from app.parsers.ecdict import EcdictParser
from app.parsers.mdict import MDictParser, read_style_context
from app.parsers.stardict import StarDictParser, parse_ifo
from app.schemas.dictionary import VALID_FORMATS
from app.services.audit_service import log_action
from app.services.background_task_service import background_tasks
from app.services.definition_repair import (
    dictionaries_using_style_markers,
    expand_stored_styles,
    remove_missing_uss_speakers,
)
from app.services.entry_scope import current_generation_only, in_dictionary_for_id_window
from app.services.language_detect import detect_language
from app.services.resource_service import SIBLING_RESOURCE_EXTENSIONS, copy_sibling_resources

logger = logging.getLogger("mydict.dictionary")

BATCH_SIZE = 2000

# 重新解析删除上一代词条时每批的行数：每批一个短事务，不长时间占着 SQLite 的写锁
_PURGE_BATCH_SIZE = 20_000

# 正在重新解析的词典 id。同一部词典并发重解析会各自写一代、互相清掉对方的行
_reparsing: set[int] = set()
_reparsing_lock = threading.Lock()

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
#
# mdict 额外允许 MDict 的附属资源（CSS/字体/JS/图片）——它们按惯例放在 .mdx 同级目录，
# 词条里的 <link href="oxbw.css"> 就指着它们。只收 .mdx/.mdd 会让上传的词典丢样式。
# 伪装成词典仍不可行：解析阶段没有 .mdx 会直接报错。
_ALLOWED_EXTENSIONS: dict[str, set[str]] = {
    "mdict": {".mdx", ".mdd"} | SIBLING_RESOURCE_EXTENSIONS,
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
        db.commit()
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


def _resolve_target_dictionaries(db: Session, dictionary_ids: list[int] | None) -> list[Dictionary]:
    """解析要处理的词典；传了 id 就按传入顺序返回，任一个不存在就整体拒绝。"""
    query = db.query(Dictionary)
    if not dictionary_ids:
        return query.order_by(Dictionary.sort_order, Dictionary.id).all()
    unique = list(dict.fromkeys(dictionary_ids))
    found = {d.id: d for d in query.filter(Dictionary.id.in_(unique)).all()}
    missing = [dict_id for dict_id in unique if dict_id not in found]
    if missing:
        raise NotFoundError(f"包含不存在的词典 ID：{missing}")
    return [found[dict_id] for dict_id in unique]


def start_reparse(db: Session, dictionary_ids: list[int] | None, settings: Settings) -> int:
    """登记「重新解析」后台任务，返回 task_id；dictionary_ids 为空表示全部词典。

    修「同名词词条被去重丢掉」用的：早先的导入按 `UNIQUE(dictionary_id, word)` 只保留每个
    词头的首条，在 63 部词典上静默丢了 1,445,181 条。约束去掉之后，**已入库的数据不会自动
    长出缺失的那些行**，需要重读一遍源文件重新入库。

    **原地**：词典 id 不变——Token/用户的「可用词典」白名单、生词本（存的是词典 id 加释义
    快照，词典本身没动）、检索范围勾选全都不用重配。词条 id 会变，但没有任何数据引用它。

    全量重灌而不是只补缺失行：此前有几轮导入期改写修复，老行是老规则产出的，只补缺失会把
    新旧两种格式混在同一部词典里。

    新词条写成下一代，写完只改 `active_generation` 一行即完成切换，见 `_reparse_one`。
    中途失败时旧词条原封不动，重跑即可。
    """
    target_ids = [d.id for d in _resolve_target_dictionaries(db, dictionary_ids)]
    with _reparsing_lock:
        busy = _reparsing.intersection(target_ids)
        if busy:
            raise ConflictError(f"词典 {sorted(busy)} 正在重新解析，请等它结束")
        _reparsing.update(target_ids)
    try:
        task = background_tasks.start("dictionary_reparse", "重新解析词典")
        threading.Thread(
            target=_run_reparse_in_background,
            args=(task.id, target_ids, settings),
            daemon=True,
        ).start()
    except Exception:
        with _reparsing_lock:
            _reparsing.difference_update(target_ids)
        raise
    return task.id


def _run_reparse_in_background(
    task_id: int, dictionary_ids: list[int], settings: Settings
) -> None:
    """后台线程入口：请求生命周期已经结束，不能沿用请求的 db session，这里单独开一个。"""
    db = SessionLocal()
    try:
        total = len(dictionary_ids)
        reparsed = 0
        skipped = 0
        entries_total = 0
        for index, dict_id in enumerate(dictionary_ids, start=1):
            dictionary = db.get(Dictionary, dict_id)
            if dictionary is None:  # 期间被删掉了
                continue
            paths = source_paths_for(dictionary)
            if not paths:
                # 源文件不在（导入后挪走了/删了）——这部词典没法重解析，跳过并计数
                skipped += 1
                background_tasks.update_progress(task_id, {"done": index, "total": total})
                continue

            def on_progress(
                done: int, _task_id: int = task_id, _index: int = index, _total: int = total
            ) -> None:
                # 里层的词条级进度对外展示成「词典 x / y · 已写入 n 条」，让用户知道没卡死
                background_tasks.update_progress(
                    _task_id, {"done": _index - 1, "total": _total, "entries": done}
                )

            count = _reparse_one(db, dictionary, paths, settings, on_progress)
            reparsed += 1
            entries_total += count
            background_tasks.update_progress(task_id, {"done": index, "total": total})

        background_tasks.succeed(
            task_id, {"dictionaries": reparsed, "entries": entries_total, "skipped": skipped}
        )
    except Exception:
        logger.exception("重新解析词典失败")
        background_tasks.fail(task_id, "重新解析失败：服务器内部错误，请查看后端日志")
    finally:
        db.close()
        with _reparsing_lock:
            _reparsing.difference_update(dictionary_ids)


def _reparse_one(
    db: Session, dictionary: Dictionary, paths: list[Path], settings: Settings, on_progress
) -> int:
    """重新解析一部词典，返回新的词条数。

    1. 解析并写入下一代（generation = active_generation + 1），每批提交。这一步最慢，
       但新行对查询不可见，旧词条照常可查；写锁只在每批提交时短暂持有。
    2. 切换：只改 `dictionaries.active_generation` 一行，查询从这一刻起只看新一代——
       原子、瞬时，不存在新旧混杂的中间态。
    3. 分批删掉旧一代（此时它们已不可见）。

    资源按「只补缺失、不覆盖」处理：词典正在服务，覆盖已有文件会让并发请求读到半截内容，
    而且大词典的 res/ 有几十万个文件，全量重写没有必要。
    """
    dict_id = dictionary.id
    current = dictionary.active_generation
    # 上次中断留下的半代
    _purge_generations(db, dict_id, DictEntry.generation != current)

    next_generation = current + 1
    parser = _PARSERS[dictionary.format]()
    res_dir = Path(settings.dictionary_storage_path) / str(dict_id) / "res"
    # 勾了「不导入发音/图片」的词典没有 res/，parse 的 resource_dir 传 None：
    # 释义不做资源引用改写，与当初导入时的行为一致
    resource_dir = res_dir if res_dir.is_dir() else None
    try:
        count = _batch_insert(
            db,
            dict_id,
            parser.parse(
                paths,
                dictionary_id=dict_id,
                resource_dir=resource_dir,
                overwrite_resources=False,
            ),
            on_progress=on_progress,
            generation=next_generation,
            commit_each_batch=True,
        )
    except Exception:
        db.rollback()
        _purge_generations(db, dict_id, DictEntry.generation == next_generation)
        raise

    dictionary.active_generation = next_generation
    dictionary.word_count = count
    db.commit()
    # 缓存里的结果还是上一代的条目（条目 id 已换）
    invalidate_query_cache()

    _purge_generations(db, dict_id, DictEntry.generation != next_generation)
    return count


def _purge_generations(db: Session, dictionary_id: int, condition) -> None:
    """按主键区间分批删掉这部词典里满足 condition 的词条，每批一个短事务。"""
    lowest, highest = db.execute(
        select(func.min(DictEntry.id), func.max(DictEntry.id)).where(
            DictEntry.dictionary_id == dictionary_id, condition
        )
    ).one()
    if lowest is None:
        return
    cursor = lowest - 1
    while cursor < highest:
        upper = min(cursor + _PURGE_BATCH_SIZE, highest)
        db.execute(
            delete(DictEntry).where(
                in_dictionary_for_id_window(dictionary_id),
                DictEntry.id > cursor,
                DictEntry.id <= upper,
                condition,
            )
        )
        db.commit()
        cursor = upper


def start_source_repair(
    db: Session, dictionary_ids: list[int] | None, settings: Settings
) -> int:
    """登记「从源文件修复」后台任务，返回 task_id；dictionary_ids 为空表示全部词典。

    修的是「导入时漏掉、只存在于源文件里的东西」，一次做两件事：

    1. **补齐 `.mdx` 同级的附属资源**（CSS/字体/脚本/图片）。早期导入只解包 `.mdd`，
       而这些文件按 MDict 惯例就躺在 `.mdx` 旁边，于是 63 部词典全部 404——图标按原始
       像素渲染（大辞泉的发音图标 75×74、岩波的派生語图标 387×150）、表格丢掉边框。
    2. **展开词条里的 `` `编号` `` 样式标记**。规则来自 `.mdx` 头部的 `StyleSheet` 字段，
       此前完全没处理，于是 `` `1` `` `` `2` `` 直接显示出来（多功能汉语辞典全部 10 万条中招）。

    两者都**不需要重新导入任何词典**。跑完会使查询结果缓存失效——释义被就地改写了，
    缓存里还存着旧快照。
    """
    targets = _resolve_target_dictionaries(db, dictionary_ids)
    task = background_tasks.start("dictionary_source_repair", "从源文件修复")
    threading.Thread(
        target=_run_source_repair_in_background,
        args=(task.id, [d.id for d in targets], settings),
        daemon=True,
    ).start()
    return task.id


def _source_files(dictionary: Dictionary) -> list[Path]:
    """`file_path` 里记录的那些源文件路径（`dicts_dir` 存文件列表、`upload` 存 source/ 目录）。"""
    return [
        Path(raw.strip()) for raw in (dictionary.file_path or "").split(";") if raw.strip()
    ]


def _source_style_context(sources: list[Path]) -> tuple[dict[str, tuple[str, str]], bool]:
    """从这部词典的 `.mdx` 里读 `StyleSheet`；读不到就返回空表。

    调用方已经确认过这部词典的词条里真的含反引号，所以这里才敢打开 `.mdx`——打开会把整份
    词头索引读进内存。源文件被删、或是不支持的压缩（LZO）导致打不开时，只记一条 warning
    并返回空表 + False：这类词典仍可正常查词，只是这条存量修复做不了。
    """
    for source in sources:
        path = source
        if path.is_dir():
            found = sorted(path.glob("*.mdx"))
            if not found:
                continue
            path = found[0]
        if path.suffix.lower() != ".mdx" or not path.is_file():
            continue
        try:
            return read_style_context(path)
        except Exception:
            logger.warning("读取 %s 的 StyleSheet 失败，跳过样式展开", path, exc_info=True)
    return {}, False


def _run_source_repair_in_background(
    task_id: int, dictionary_ids: list[int], settings: Settings
) -> None:
    """后台线程入口：请求生命周期已经结束，不能沿用请求的 db session，这里单独开一个。"""
    db = SessionLocal()
    try:
        total = len(dictionary_ids)
        repaired = 0
        copied = 0
        styled_dictionaries = 0
        styled_entries = 0
        # 先定位「词条里真的含反引号」的词典，只对这些打开 .mdx（见该函数的注释）
        with_markers = dictionaries_using_style_markers(db, set(dictionary_ids))
        for index, dict_id in enumerate(dictionary_ids, start=1):
            dictionary = db.get(Dictionary, dict_id)
            if dictionary is None:  # 修复期间被删掉了
                continue
            sources = _source_files(dictionary)
            # 不检查 res/ 是否已存在——`copy_sibling_resources` 会按需建目录。
            # 曾经这里加过「没有 res/ 就跳过，说明用户当初勾了 skip_resources」，是错的：
            # 只有 .mdx 没有 .mdd 的词典（Weblio類語辞典、moji辞書、thesaurus近反义词…）
            # 同样没有 res/，但它们的释义引用照常被改写成了 /dict-res/…，正需要这个文件。
            count = copy_sibling_resources(
                Path(settings.dictionary_storage_path) / str(dict_id) / "res", sources
            )
            if count:
                repaired += 1
            copied += count

            if dict_id in with_markers:
                stylesheet, compact = _source_style_context(sources)
                # 非 Compact 词典的反引号是巧合文本（见 expand_style_markers 的门控注释），
                # 修复就是空操作；Compact 词典即使样式表为空也要跑——任务是剔除标记。
                if compact:
                    changed = expand_stored_styles(
                        db, dict_id, stylesheet, compact=compact
                    )
                    if changed:
                        styled_dictionaries += 1
                        styled_entries += changed
            background_tasks.update_progress(task_id, {"done": index, "total": total})

        if styled_entries:
            # 释义被就地改写，进程内的查询结果缓存里还存着旧快照（TTL 300s）。
            # 应用内后台任务能直接清掉它，不需要像 CLI 那样重启容器。
            invalidate_query_cache()
        background_tasks.succeed(
            task_id,
            {
                "dictionaries": repaired,
                "files": copied,
                "styled_dictionaries": styled_dictionaries,
                "styled_entries": styled_entries,
            },
        )
    except Exception:
        logger.exception("从源文件修复失败")
        background_tasks.fail(task_id, "修复失败：服务器内部错误，请查看后端日志")
    finally:
        db.close()


def start_uss_cleanup(db: Session, dictionary_id: int, settings: Settings) -> int:
    """登记「清理缺失的红色美音例句喇叭」后台任务，返回 task_id。

    牛津高阶第9版的例句配了一对喇叭，红色美音（audio-uss-liju）指向的 mp3 源词典就基本
    没打包（实测 99% 缺失），点它必弹「发音不存在或解码失败」。这个任务把**指向缺失文件**
    的红色喇叭从释义里删掉（文件还在的保留）。只处理指定词典；重新解析后喇叭会被源文件
    带回来，需要重跑。
    """
    if db.get(Dictionary, dictionary_id) is None:
        raise NotFoundError("词典不存在")
    task = background_tasks.start("dictionary_uss_cleanup", "清理缺失的美音例句喇叭")
    threading.Thread(
        target=_run_uss_cleanup_in_background,
        args=(task.id, dictionary_id, settings.dictionary_storage_path),
        daemon=True,
    ).start()
    return task.id


def _run_uss_cleanup_in_background(
    task_id: int, dictionary_id: int, storage_path: str
) -> None:
    """后台线程入口：请求生命周期已经结束，不能沿用请求的 db session，这里单独开一个。"""
    db = SessionLocal()
    try:
        res_dir = Path(storage_path) / str(dictionary_id) / "res"

        def on_progress(entries_changed: int, anchors_removed: int) -> None:
            background_tasks.update_progress(
                task_id,
                {"entries": entries_changed, "speakers": anchors_removed},
            )

        entries, speakers = remove_missing_uss_speakers(
            db, dictionary_id, res_dir, on_progress=on_progress
        )
        if entries:
            # 释义被就地改写，进程内的查询结果缓存里还存着旧快照（TTL 300s）。
            invalidate_query_cache()
        background_tasks.succeed(task_id, {"entries": entries, "speakers": speakers})
    except Exception:
        logger.exception("红色美音例句喇叭清理失败")
        background_tasks.fail(task_id, "清理失败：服务器内部错误，请查看后端日志")
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


def _batch_insert(
    db: Session,
    dictionary_id: int,
    entries,
    on_progress=None,
    *,
    generation: int = 0,
    commit_each_batch: bool = False,
) -> int:
    """把解析出的词条写入 dict_entries，返回写入行数。

    导入时整部词典在一个事务里（失败整体清理）；重新解析写的是尚不可见的下一代，
    commit_each_batch=True 每批提交，避免长时间占着写锁。

    **同名词条全部保留**：MDict 允许同一词头有多条内容不同的条目（搜韵诗词全文检索版里
    「毛泽东」有 82 条，是 82 首不同的诗词）。这里曾经按词头去重只留首条，结果在 63 部词典
    上静默丢了 1,445,181 条内容——不报错，也不体现在 word_count 里。
    """
    count = 0
    batch: list[DictEntry] = []
    for entry in entries:
        batch.append(
            DictEntry(
                dictionary_id=dictionary_id,
                word=entry.word,
                word_lower=entry.word.lower(),
                phonetic=entry.phonetic,
                definition=entry.definition,
                extra=json.dumps(entry.extra, ensure_ascii=False) if entry.extra else None,
                generation=generation,
            )
        )
        count += 1
        if len(batch) >= BATCH_SIZE:
            db.bulk_save_objects(batch)
            db.flush()
            if commit_each_batch:
                db.commit()
            batch.clear()
            if on_progress:
                on_progress(count)
    if batch:
        db.bulk_save_objects(batch)
        db.flush()
        if commit_each_batch:
            db.commit()
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


def rename_dictionaries(
    db: Session,
    *,
    pattern: str,
    replacement: str,
    dictionary_ids: list[int] | None,
    dry_run: bool,
    admin_id: int,
) -> dict:
    """按正则批量重命名词典。

    pattern 用 Python re 语法，replacement 支持 ``\\1`` 这类反向引用；dictionary_ids 留空表示
    对全部词典生效。只动 name——format 决定当初怎么解析入库、改名不会重新解析，语言方向另有
    批量识别的入口。

    先预览（dry_run=True）再应用是刻意的：正则是全局替换，一次写错就能改坏几十部词典名，
    而名字是用户唯一认得出哪部是哪部的标识。
    """
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise ValidationAppError(f"正则表达式无效：{exc}") from exc

    query = db.query(Dictionary)
    if dictionary_ids:
        query = query.filter(Dictionary.id.in_(list(dict.fromkeys(dictionary_ids))))

    items: list[dict] = []
    for dictionary in query.order_by(Dictionary.sort_order, Dictionary.id).all():
        new_name = compiled.sub(replacement, dictionary.name).strip()
        # 改成空名或超长名的跳过：留一个不可用的名字比不改更糟
        if not new_name or new_name == dictionary.name or len(new_name) > 255:
            continue
        items.append({"id": dictionary.id, "name": dictionary.name, "new_name": new_name})

    if not dry_run and items:
        try:
            for item in items:
                db.get(Dictionary, item["id"]).name = item["new_name"]
            db.commit()
        except Exception:
            db.rollback()
            raise
        for item in items:
            log_action(
                db,
                actor_type="admin",
                actor_id=admin_id,
                action="dictionary.rename",
                target=str(item["id"]),
                detail={"from": item["name"], "to": item["new_name"]},
            )
        # 查询结果的缓存里带着词典名称快照
        invalidate_query_cache()

    return {"items": items, "applied": not dry_run}


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
        current_generation_only(db.query(DictEntry))
        .filter(
            DictEntry.dictionary_id == dictionary_id, DictEntry.word_lower.like(f"{word_lower}%")
        )
        .order_by(DictEntry.word_lower)
        .limit(limit)
        .all()
    )
