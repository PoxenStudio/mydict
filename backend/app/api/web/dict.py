import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core import rate_limiter
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.deps import WebCaller, get_web_caller, require_user
from app.core.exceptions import RateLimitedError
from app.models.user import User
from app.schemas.query import PublicDictionaryOut, QueryHistoryResponse, QueryResponse
from app.services import query_log_service, query_service
from app.services.settings_service import get_int_setting

router = APIRouter(prefix="/dict", tags=["web-dict"])


@router.get("/dictionaries", response_model=list[PublicDictionaryOut])
def list_dictionaries(db: Session = Depends(get_db)) -> list[PublicDictionaryOut]:
    """供前台「词典选择」弹窗展示全部已启用词典，不受当前用户自己的可用词典限制——
    那是用来配置限制的，如果被限制过滤了就没法再选回来。"""
    return query_service.list_public_dictionaries(db)


@router.get("/search", response_model=QueryResponse)
def search(
    word: str,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    caller: WebCaller = Depends(get_web_caller),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> QueryResponse:
    # 登录用户不做限流；访客与匿名 API 调用共用同一套按 IP 限流规则。
    if caller.user is None:
        limit = get_int_setting(
            db, "anonymous_ip_rate_limit_per_min", settings.anonymous_ip_rate_limit_per_min
        )
        if not rate_limiter.check_and_increment(caller.ip or "unknown", limit):
            query_log_service.log_query(
                db, source="web", word=word, status="rate_limited", duration_ms=0, ip=caller.ip
            )
            raise RateLimitedError(
                "查询过于频繁，请稍后再试", retry_after=rate_limiter.seconds_to_next_minute()
            )

    allowed_ids = caller.user.allowed_dictionary_ids if caller.user else None
    started = time.perf_counter()
    results = query_service.search_word(db, word, None, from_, to, allowed_ids)
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


@router.get("/history", response_model=QueryHistoryResponse)
def history(user: User = Depends(require_user), db: Session = Depends(get_db)) -> QueryHistoryResponse:
    return QueryHistoryResponse(items=query_log_service.get_recent_history(db, user.id, 100))
