"""随机浏览词条端点。

「随机」模式的后端：只负责挑一条，返回词典与词条标识；前端再用既有的词条文档接口渲染，
渲染、收藏、发音全部复用。算法见 random_entry_service。

计次与查询一致（走同一个按 IP 限额），但不写入查询历史——浏览不是检索。
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.deps import WebCaller, get_web_caller
from app.services import random_entry_service, web_rate_limit_service

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
    web_rate_limit_service.enforce_query_limit(db, caller, settings, "随机浏览")

    wanted = {int(x) for x in dict_ids.split(",") if x.strip().isdigit()} if dict_ids else None
    allowed_ids = caller.user.allowed_dictionary_ids if caller.user else None
    dictionary, entry = random_entry_service.pick_random_entry(db, wanted, allowed_ids)
    return RandomEntryOut(
        dictionary_id=dictionary.id,
        dictionary_name=dictionary.name,
        word=entry.word,
        entry_id=entry.id,
    )
