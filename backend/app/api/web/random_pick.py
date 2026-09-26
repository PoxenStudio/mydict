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
from app.services.query_service import current_generation_only

router = APIRouter(prefix="/dict", tags=["web-dict"])


class RandomEntryOut(BaseModel):
    dictionary_id: int
    dictionary_name: str
    word: str
    entry_id: int


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
        (lo, hi) = db.execute(
            select(func.min(DictEntry.id), func.max(DictEntry.id)).where(
                DictEntry.dictionary_id == dictionary.id
            )
        ).one()
        if lo is None or hi is None or hi <= lo:
            continue
        spans.append((dictionary, lo, hi))
    if not spans:
        raise NotFoundError("随机浏览的词典池为空")

    total_span = sum(hi - lo + 1 for _, lo, hi in spans)
    pick = random.randint(0, total_span - 1)
    chosen: tuple[Dictionary, int, int] | None = None
    for dictionary, lo, hi in spans:
        span = hi - lo + 1
        if pick < span:
            chosen = (dictionary, lo, hi)
            break
        pick -= span
    assert chosen is not None
    dictionary, lo, hi = chosen

    # 区间内随机落点，取落点之后的第一条（主键定位，瞬时）
    entry = (
        current_generation_only(db.query(DictEntry))
        .filter(
            DictEntry.dictionary_id == dictionary.id,
            DictEntry.id >= random.randint(lo, hi),
        )
        .order_by(DictEntry.id)
        .first()
    )
    if entry is None:  # 落点之后没有活跃代的词条：退回区间开头
        entry = (
            current_generation_only(db.query(DictEntry))
            .filter(DictEntry.dictionary_id == dictionary.id)
            .order_by(DictEntry.id)
            .first()
        )
    if entry is None:
        raise NotFoundError("随机浏览的词典池为空")

    return RandomEntryOut(
        dictionary_id=dictionary.id,
        dictionary_name=dictionary.name,
        word=entry.word,
        entry_id=entry.id,
    )
