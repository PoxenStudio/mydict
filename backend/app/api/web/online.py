"""在线词典查询端点（维基百科 / 维基词典 / 百度百科 / 外部搜索链接）。

出站抓取在本服务端做（百度百科无 CORS 且要求手机 UA；维基两家的 REST 接口虽然
CORS 开放，但统一走服务端可以加缓存、限流，也避免把用户 IP 直接暴露给第三方）。
返回的是**纯文本**结构化结果——第三方 HTML 不进前端，没有注入面。

不计入查询配额：它不是词典查询，走独立的按 IP 限额（查询限额的一半），防止
被当成匿名抓取代理。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.deps import WebCaller, get_web_caller
from app.schemas.query import OnlineLookupResponse
from app.services import online_dict_service, web_rate_limit_service

router = APIRouter(prefix="/dict", tags=["web-dict"])


@router.get("/online/lookup", response_model=OnlineLookupResponse)
def online_lookup(
    word: str,
    lang: str = Query("zh", pattern="^[a-z]{2}(-[A-Za-z]{2,4})?$"),
    caller: WebCaller = Depends(get_web_caller),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OnlineLookupResponse:
    web_rate_limit_service.enforce_online_limit(db, caller, settings)
    data = online_dict_service.lookup_with_settings(db, settings, word, lang)
    return OnlineLookupResponse(**data)
