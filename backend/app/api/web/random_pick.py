"""随机浏览词条端点。

「随机」模式的后端：在调用方有权访问的词典范围里随机挑一条词条，返回
词典与词条标识，前端再用既有的词条文档接口渲染——渲染、收藏、发音全部复用，
这里只负责「挑一条」。

随机算法：每部词典先取主键区间 `MIN(id)/MAX(id)`（主键索引，O(1)），按区间大小
加权随机挑一部词典，再在区间里随机落一个点、取 `id >= 点` 的第一条（同样是主键
区间定位，826 万行的词典也是毫秒级）。id 空洞会让分布略有偏倚，对「随便看看」
无伤大雅；`ORDER BY RANDOM()` 的全表扫描才是不可接受的。

计次与查询一致（走同一个按 IP 限额），但不写入查询历史——浏览不是检索。
"""

import random

from cachetools import TTLCache
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.web.dict import _enforce_web_rate_limit
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.deps import WebCaller, get_web_caller
from app.core.exceptions import NotFoundError
from app.models.dictionary import DictEntry, Dictionary

router = APIRouter(prefix="/dict", tags=["web-dict"])

# 主键区间缓存：`MAX(id) WHERE dictionary_id=?` 会扫整部词典的索引（搜韵 826 万行，
# 69 部逐个算要 2.5 秒），而区间在两次导入之间基本不变——10 分钟 TTL 自愈足够。
_BOUNDS_CACHE: TTLCache = TTLCache(maxsize=1000, ttl=600)


class RandomEntryOut(BaseModel):
    dictionary_id: int
    dictionary_name: str
    word: str
    entry_id: int


def _random_entry_in_span(db: Session, dictionary: Dictionary, lo: int, hi: int) -> DictEntry | None:
    """在词典主键区间里随机取一条**当前代**的词条。

    不能把 dictionary_id/generation 塞进 SQL：`dictionary_id=? AND id>=?` 会让规划器放弃
    主键、走 (dictionary_id, word_lower) 覆盖索引扫整部词典再排序（搜韵实测 2.1 秒）。
    这里用纯主键游标跳步（毫秒级）：词条 id 按导入批次成块聚集，通常一两步就命中本词典；
    跨代/他词典的行在 Python 侧跳过，50 步封底后返回 None 由调用方换词典。
    """
    active = dictionary.active_generation
    cursor = random.randint(lo, hi)
    for _ in range(50):
        row = db.execute(
            select(DictEntry.id).where(DictEntry.id >= cursor).order_by(DictEntry.id).limit(1)
        ).one_or_none()
        if row is None:
            return None
        entry_id = row[0]
        entry = db.get(DictEntry, entry_id)
        if (
            entry is not None
            and entry.dictionary_id == dictionary.id
            and entry.generation == active
        ):
            return entry
        cursor = entry_id + 1
    return None


@router.get("/random", response_model=RandomEntryOut)
def random_entry(
    dict_ids: str | None = Query(None, description="逗号分隔的词典 id；空 = 全部可用词典"),
    caller: WebCaller = Depends(get_web_caller),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RandomEntryOut:
    _enforce_web_rate_limit(db, caller, settings, "随机浏览")

    wanted = {int(x) for x in dict_ids.split(",") if x.strip().isdigit()} if dict_ids else None
    query = db.query(Dictionary).filter(Dictionary.status == "enabled")
    allowed_ids = caller.user.allowed_dictionary_ids if caller.user else None
    if allowed_ids is not None:
        query = query.filter(Dictionary.id.in_(allowed_ids))
    if wanted:
        query = query.filter(Dictionary.id.in_(wanted))
    dictionaries = query.all()
    if not dictionaries:
        raise NotFoundError("随机浏览的词典池为空")

    # 按主键区间大小加权随机挑词典；区间查不到（空词典）就跳过
    spans: list[tuple[Dictionary, int, int]] = []
    for dictionary in dictionaries:
        if dictionary.id in _BOUNDS_CACHE:
            lo, hi = _BOUNDS_CACHE[dictionary.id]
        else:
            (lo, hi) = db.execute(
                select(func.min(DictEntry.id), func.max(DictEntry.id)).where(
                    DictEntry.dictionary_id == dictionary.id
                )
            ).one()
            if lo is None or hi is None:
                continue
            _BOUNDS_CACHE[dictionary.id] = (lo, hi)
        if hi <= lo:
            continue
        spans.append((dictionary, lo, hi))
    if not spans:
        raise NotFoundError("随机浏览的词典池为空")

    total_span = sum(hi - lo + 1 for _, lo, hi in spans)
    pick = random.randint(0, total_span - 1)
    start = 0
    for index, (dictionary, lo, hi) in enumerate(spans):
        if pick < hi - lo + 1:
            start = index
            break
        pick -= hi - lo + 1
    # 加权随机选中一部词典；它随机落点失败（区间尾巴全是别家/旧代的行）就顺位换下一部
    ordered = spans[start:] + spans[:start]
    entry: DictEntry | None = None
    chosen: Dictionary | None = None
    for dictionary, lo, hi in ordered:
        entry = _random_entry_in_span(db, dictionary, lo, hi)
        if entry is not None:
            chosen = dictionary
            break
    if entry is None or chosen is None:
        raise NotFoundError("随机浏览的词典池为空")

    return RandomEntryOut(
        dictionary_id=chosen.id,
        dictionary_name=chosen.name,
        word=entry.word,
        entry_id=entry.id,
    )
