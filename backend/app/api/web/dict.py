import time
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core import rate_limiter
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.deps import WebCaller, get_web_caller, require_user
from app.core.exceptions import NotFoundError, RateLimitedError
from app.models.dictionary import Dictionary
from app.models.user import User
from app.schemas.query import PublicDictionaryOut, QueryHistoryResponse, QueryResponse
from app.services import query_log_service, query_service
from app.services.entry_render_service import render_entry_document
from app.services.settings_service import get_int_setting

router = APIRouter(prefix="/dict", tags=["web-dict"])


def _enforce_web_rate_limit(db: Session, caller: WebCaller, settings: Settings, word: str) -> None:
    """访客与匿名 API 调用共用同一套按 IP 限流规则；登录用户走单独的（通常更宽松的）按 IP
    限流阈值。计数 key 按登录态区分前缀，避免同一 IP 下匿名与登录用户互相挤占对方的配额。
    """
    ip = caller.ip or "unknown"
    if caller.user is None:
        limit = get_int_setting(
            db, "anonymous_ip_rate_limit_per_min", settings.anonymous_ip_rate_limit_per_min
        )
        counter_key = f"anon:{ip}"
    else:
        limit = get_int_setting(
            db, "user_ip_rate_limit_per_min", settings.user_ip_rate_limit_per_min
        )
        counter_key = f"user:{ip}"
    if rate_limiter.check_and_increment(counter_key, limit):
        return
    query_log_service.log_query(
        db,
        source="web",
        word=word,
        status="rate_limited",
        duration_ms=0,
        user_id=caller.user.id if caller.user else None,
        ip=caller.ip,
    )
    raise RateLimitedError(
        "查询过于频繁，请稍后再试", retry_after=rate_limiter.seconds_to_next_minute()
    )


@router.get("/dictionaries", response_model=list[PublicDictionaryOut])
def list_dictionaries(db: Session = Depends(get_db)) -> list[PublicDictionaryOut]:
    """供前台「词典选择」弹窗展示全部已启用词典，不受当前用户自己的可用词典限制——
    那是用来配置限制的，如果被限制过滤了就没法再选回来。"""
    return query_service.list_public_dictionaries(db)


@router.get("/search", response_model=QueryResponse)
def search(
    word: str,
    dict: str | None = None,  # noqa: A002 - 与 API 契约中的查询参数名保持一致
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    caller: WebCaller = Depends(get_web_caller),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> QueryResponse:
    _enforce_web_rate_limit(db, caller, settings, word)

    allowed_ids = caller.user.allowed_dictionary_ids if caller.user else None
    started = time.perf_counter()
    results = query_service.search_word(
        db, word, query_service.parse_dict_ids(dict), from_, to, allowed_ids
    )
    duration_ms = int((time.perf_counter() - started) * 1000)

    query_log_service.log_query(
        db,
        source="web",
        word=word,
        status="success" if results else "not_found",
        duration_ms=duration_ms,
        user_id=caller.user.id if caller.user else None,
        dictionary_id=results[0]["dictionary_id"] if results else None,
        ip=caller.ip,
    )
    return QueryResponse(results=results)


@router.get("/entry/{dictionary_id}", response_class=HTMLResponse)
def entry_document(
    dictionary_id: int,
    word: str,
    theme: Literal["light", "dark"] | None = None,
    caller: WebCaller = Depends(get_web_caller),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """把单条词条的释义渲染成独立 HTML 文档，供前端放进隔离 iframe。

    前端用 axios 带 token 取回内容后塞进 srcdoc，而不是让 iframe 直接导航到这里：
    iframe 导航不会带 Authorization 头，端点就只能匿名开放，会绕过 Token 的
    「可用词典」限制。

    刻意**不**计入按 IP 的查询配额：它是一次已经计过配额的查询的子请求，按部计费会让
    「展开 N 部词典」变成 N+1 次配额；而且它一次只返回一条词条，比 /search 一次返回
    全部命中词典的释义暴露更少。

    theme 由前端按当前主题带上：直接写进文档，iframe 首屏就是正确的明暗，不必等父页的
    postMessage 到达再变色（那会有一次肉眼可见的闪变）。
    """
    dictionary = db.get(Dictionary, dictionary_id)
    allowed_ids = caller.user.allowed_dictionary_ids if caller.user else None
    if (
        dictionary is None
        or dictionary.status != "enabled"
        or (allowed_ids and dictionary_id not in allowed_ids)
    ):
        # 未启用 / 不在授权范围内 / 不存在，统一 404，不泄漏词典是否存在
        raise NotFoundError("词条不存在")

    entry = query_service.get_entry(db, dictionary_id, word)
    if entry is None:
        raise NotFoundError("词条不存在")

    return HTMLResponse(
        render_entry_document(
            # allow_lookup：只有前台查询页有查词框能接住「选中文字查词」这个动作
            entry.definition,
            dictionary_id=dictionary_id,
            theme=theme,
            allow_lookup=True,
        )
    )


@router.get("/history", response_model=QueryHistoryResponse)
def history(
    user: User = Depends(require_user), db: Session = Depends(get_db)
) -> QueryHistoryResponse:
    return QueryHistoryResponse(items=query_log_service.get_recent_history(db, user.id, 100))
