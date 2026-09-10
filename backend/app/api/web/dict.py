import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import rate_limiter
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.deps import WebCaller, get_web_caller
from app.core.exceptions import RateLimitedError
from app.schemas.query import QueryResponse
from app.services import query_log_service, query_service
from app.services.settings_service import get_int_setting

router = APIRouter(prefix="/dict", tags=["web-dict"])


@router.get("/search", response_model=QueryResponse)
def search(
    word: str,
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
            raise RateLimitedError(
                "查询过于频繁，请稍后再试", retry_after=rate_limiter.seconds_to_next_minute()
            )

    started = time.perf_counter()
    results = query_service.search_word(db, word)
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
