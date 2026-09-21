"""修复历史遗留的坏资源链接。

`rewrite_resource_refs()` 早期版本把 `entry://` 与 `sound://` 也当成词典内部资源相对路径，
改写成了指向不存在位置的 URL：

    entry://苹果          -> /dict-res/7/res/entry:/苹果
    sound://audio/x.spx   -> /dict-res/7/res/sound:/audio/x.spx

导入代码已经修好（新导入的词典不会再产生这种值），但**已入库的行不会自动恢复**，
所以需要这个一次性的修复动作。它是纯字符串替换，结果与新导入代码产出的值逐条一致。

刻意不做的事：
  - 不恢复 `javascript:` / `file://`（那些本来就不该被改成可访问的 URL）
  - 不尝试还原 `//host/path` 与 `www.host/path`（旧改写把它们变成了
    `/dict-res/{id}/res/host/path`，与真实的资源路径已经无法区分）
"""

import logging
from collections.abc import Callable

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.models.dictionary import DictEntry

logger = logging.getLogger("mydict.dictionary")

# 单批处理的主键区间大小。SQLite 一次 UPDATE 的行数不宜过大：大事务会长时间持有写锁，
# 与正在服务的查询互相阻塞；分批 commit 也让中断后重跑只损失最后一批。
DEFAULT_BATCH_SIZE = 5000

_ENTRY_SUFFIX = "entry:/"
_SOUND_SUFFIX = "sound:/"


def _prefixes(dictionary_id: int) -> tuple[str, str, str]:
    """返回 (坏 entry 前缀, 坏 sound 前缀, 资源前缀)。"""
    base = f"/dict-res/{dictionary_id}/res/"
    return base + _ENTRY_SUFFIX, base + _SOUND_SUFFIX, base


def count_legacy_links(db: Session, dictionary_id: int) -> tuple[int, int]:
    """统计该词典里含坏 entry / 坏 sound 链接的行数（只读，供 dry-run 与进度预估）。"""
    entry_like = f"%{_prefixes(dictionary_id)[0]}%"
    sound_like = f"%{_prefixes(dictionary_id)[1]}%"
    # 用 FILTER 一次扫描同时拿到两个计数；分两条 SQL 会把该词典的 definition 读两遍。
    row = db.execute(
        select(
            func.count().filter(DictEntry.definition.like(entry_like)),
            func.count().filter(DictEntry.definition.like(sound_like)),
        ).where(DictEntry.dictionary_id == dictionary_id)
    ).one()
    return int(row[0] or 0), int(row[1] or 0)


def repair_legacy_links(
    db: Session,
    dictionary_id: int,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
) -> int:
    """修复某部词典里全部坏链接，返回实际改动的行数。

    dry_run=True 时只统计不改写。按主键区间分批（而不是按 (dictionary_id, word) 唯一索引），
    这样每批只扫一段连续区间；用唯一索引反而会因为排序是 word 导致每批都重扫。
    """
    entry_from, sound_from, res_prefix = _prefixes(dictionary_id)
    entry_like = f"%{entry_from}%"
    sound_like = f"%{sound_from}%"

    bounds = db.execute(
        select(func.min(DictEntry.id), func.max(DictEntry.id)).where(
            DictEntry.dictionary_id == dictionary_id
        )
    ).one()
    lowest, highest = bounds
    if lowest is None or highest is None:
        return 0

    if dry_run:
        entry_count, sound_count = count_legacy_links(db, dictionary_id)
        logger.info(
            "词典 %s 待修复：entry %s 行、sound %s 行（dry-run，未写入）",
            dictionary_id,
            entry_count,
            sound_count,
        )
        return entry_count + sound_count

    # entry 的替换必须排在 sound 之前（内层先执行）；两者结果互不包含，顺序只是保持确定性。
    new_definition = func.replace(
        func.replace(DictEntry.definition, entry_from, "entry://"), sound_from, res_prefix
    )

    repaired = 0
    scanned = 0
    cursor = lowest - 1
    while cursor < highest:
        window_end = min(cursor + batch_size, highest)
        result = db.execute(
            update(DictEntry)
            .where(
                DictEntry.id > cursor,
                DictEntry.id <= window_end,
                or_(DictEntry.definition.like(entry_like), DictEntry.definition.like(sound_like)),
            )
            .values(definition=new_definition)
        )
        db.commit()
        repaired += result.rowcount or 0
        cursor = window_end
        scanned += 1
        if on_progress is not None:
            on_progress(repaired, cursor - lowest)
    logger.info("词典 %s 修复完成：改动 %s 行（扫了 %s 批）", dictionary_id, repaired, scanned)
    return repaired
