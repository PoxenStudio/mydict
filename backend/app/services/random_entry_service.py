"""随机浏览：在调用方可用的词典范围里随机挑一条当前代的词条。

每部词典先取主键区间 `MIN(id)/MAX(id)`，按区间大小加权随机挑一部词典，再在区间里随机
落一个点、取 `id >= 点` 的第一条（主键区间定位，826 万行的词典也是毫秒级）。id 空洞会让
分布略有偏倚，对「随便看看」无伤大雅；`ORDER BY RANDOM()` 的全表扫描才是不可接受的。
"""

import logging
import random
import threading
from threading import Lock

from cachetools import TTLCache
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.exceptions import NotFoundError
from app.models.dictionary import DictEntry, Dictionary

logger = logging.getLogger("mydict.random")

# 主键区间缓存：`MAX(id) WHERE dictionary_id=?` 会扫整部词典的索引（搜韵 826 万行，
# 69 部逐个算要 2.3 秒），而区间只在导入/重新解析/删除时变——这几处主动失效，TTL 兜底。
# TTL 取 1 小时：它同时是「闲置后重算的间隔」与「万一漏了失效的坏窗口」，1 小时两头都够用
# （TTL 更长收益不再增加，坏窗口却线性变长）。
_BOUNDS_CACHE: TTLCache = TTLCache(maxsize=1000, ttl=3600)
_bounds_lock = Lock()
# 预热单飞：启动预热与开关翻转预热可能叠在一起，同一时刻只跑一个线程
_warming = False
_warming_lock = Lock()

_MAX_CURSOR_STEPS = 50


def invalidate_bounds() -> None:
    with _bounds_lock:
        _BOUNDS_CACHE.clear()


def warm_bounds(db: Session) -> int:
    """把全部启用词典的主键区间算进缓存，供「启动预热」与「开关翻转预热」调用。

    只是把 `_bounds` 对每部词典跑一遍（合计两秒级），预热后才点【随机】的人不必等这次扫描。
    返回预热成功的词典数。
    """
    warmed = 0
    for dictionary_id in (
        row[0] for row in db.query(Dictionary.id).filter(Dictionary.status == "enabled").all()
    ):
        if _bounds(db, dictionary_id) is not None:
            warmed += 1
    return warmed


def warm_bounds_in_background() -> bool:
    """后台线程预热区间缓存；已在预热中时直接返回 False（不排队、不叠加）。"""
    global _warming
    with _warming_lock:
        if _warming:
            return False
        _warming = True

    def run() -> None:
        global _warming
        # 预热线程自取 session：调用方（启动线程 / 设置保存请求）不会给它传连接
        db = SessionLocal()
        try:
            logger.info("开始预热随机浏览词典区间缓存")
            logger.info("随机浏览词典区间缓存预热完成：%s 部", warm_bounds(db))
        except Exception:
            logger.warning("预热随机浏览词典区间缓存失败，改由首次请求懒加载", exc_info=True)
        finally:
            db.close()
            with _warming_lock:
                _warming = False

    threading.Thread(target=run, name="mydict-random-warm", daemon=True).start()
    return True


def _bounds(db: Session, dictionary_id: int) -> tuple[int, int] | None:
    with _bounds_lock:
        cached = _BOUNDS_CACHE.get(dictionary_id)
    if cached is not None:
        return cached
    lo, hi = db.execute(
        select(func.min(DictEntry.id), func.max(DictEntry.id)).where(
            DictEntry.dictionary_id == dictionary_id
        )
    ).one()
    if lo is None or hi is None:
        return None
    with _bounds_lock:
        _BOUNDS_CACHE[dictionary_id] = (lo, hi)
    return lo, hi


def _random_entry_in_span(
    db: Session, dictionary: Dictionary, lo: int, hi: int
) -> DictEntry | None:
    """在词典主键区间里随机取一条**当前代**的词条。

    不能把 dictionary_id/generation 塞进 SQL：`dictionary_id=? AND id>=?` 会让规划器放弃
    主键、走 (dictionary_id, word_lower) 覆盖索引扫整部词典再排序（搜韵实测 2.1 秒）。
    这里用纯主键游标跳步（毫秒级）：词条 id 按导入批次成块聚集，通常一两步就命中本词典；
    跨代/他词典的行在 Python 侧跳过，步数封底后返回 None 由调用方换词典。
    """
    active = dictionary.active_generation
    cursor = random.randint(lo, hi)
    for _ in range(_MAX_CURSOR_STEPS):
        entry = db.execute(
            select(DictEntry).where(DictEntry.id >= cursor).order_by(DictEntry.id).limit(1)
        ).scalar_one_or_none()
        if entry is None:
            return None
        if entry.dictionary_id == dictionary.id and entry.generation == active:
            return entry
        cursor = entry.id + 1
    return None


def pick_random_entry(
    db: Session, dict_ids: set[int] | None, allowed_ids: list[int] | None
) -> tuple[Dictionary, DictEntry]:
    """在「已启用 ∩ 调用方可用 ∩ dict_ids」的词典池里随机挑一条；池为空时 404。"""
    query = db.query(Dictionary).filter(Dictionary.status == "enabled")
    if allowed_ids is not None:
        query = query.filter(Dictionary.id.in_(allowed_ids))
    if dict_ids:
        query = query.filter(Dictionary.id.in_(dict_ids))

    spans: list[tuple[Dictionary, int, int]] = []
    for dictionary in query.all():
        bounds = _bounds(db, dictionary.id)
        if bounds is not None:
            spans.append((dictionary, *bounds))
    if not spans:
        raise NotFoundError("随机浏览的词典池为空")

    # 按主键区间大小加权随机挑词典
    pick = random.randint(0, sum(hi - lo + 1 for _, lo, hi in spans) - 1)
    start = 0
    for index, (_, lo, hi) in enumerate(spans):
        if pick < hi - lo + 1:
            start = index
            break
        pick -= hi - lo + 1
    # 选中的词典随机落点失败（区间尾巴全是别家/旧代的行）就顺位换下一部
    for dictionary, lo, hi in spans[start:] + spans[:start]:
        entry = _random_entry_in_span(db, dictionary, lo, hi)
        if entry is not None:
            return dictionary, entry
    raise NotFoundError("随机浏览的词典池为空")
