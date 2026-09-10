import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import rate_limiter
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.deps import ApiCaller, get_api_caller
from app.core.exceptions import RateLimitedError
from app.schemas.query import PublicDictionaryOut, QueryResponse, SuggestResponse
from app.services import query_log_service, query_service, rate_limit_service
from app.services.settings_service import get_int_setting

router = APIRouter(prefix="/v1", tags=["v1-query"])


def _enforce_rate_limit(db: Session, caller: ApiCaller, settings: Settings) -> None:
    if caller.token is not None:
        default_limit = get_int_setting(
            db, "token_default_daily_limit", settings.token_default_daily_limit
        )
        if not rate_limit_service.check_and_increment_token_daily(db, caller.token, default_limit):
            raise RateLimitedError(
                "已超出今日调用次数上限", retry_after=rate_limit_service.seconds_to_tomorrow()
            )
    else:
        limit = get_int_setting(
            db, "anonymous_ip_rate_limit_per_min", settings.anonymous_ip_rate_limit_per_min
        )
        if not rate_limiter.check_and_increment(caller.ip or "unknown", limit):
            raise RateLimitedError(
                "匿名调用过于频繁，请稍后再试", retry_after=rate_limiter.seconds_to_next_minute()
            )


def _parse_dict_ids(dict_param: str | None) -> list[int] | None:
    if not dict_param:
        return None
    ids = []
    for part in dict_param.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids or None


@router.get("/query", response_model=QueryResponse)
def query_word(
    word: str,
    dict: str | None = None,  # noqa: A002 - 与 API 契约中的查询参数名保持一致
    caller: ApiCaller = Depends(get_api_caller),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> QueryResponse:
    _enforce_rate_limit(db, caller, settings)

    started = time.perf_counter()
    results = query_service.search_word(db, word, _parse_dict_ids(dict))
    duration_ms = int((time.perf_counter() - started) * 1000)

    query_log_service.log_query(
        db,
        source="api",
        word=word,
        status="success" if results else "not_found",
        duration_ms=duration_ms,
        token_id=caller.token.id if caller.token else None,
        dictionary_id=results[0]["dictionary_id"] if results else None,
        ip=caller.ip,
    )
    return QueryResponse(results=results)


@router.get("/suggest", response_model=SuggestResponse)
def suggest(
    prefix: str,
    limit: int = 10,
    dict: str | None = None,  # noqa: A002
    caller: ApiCaller = Depends(get_api_caller),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SuggestResponse:
    _enforce_rate_limit(db, caller, settings)
    words = query_service.suggest_prefix(db, prefix, _parse_dict_ids(dict), min(limit, 50))
    return SuggestResponse(words=words)


@router.get("/dictionaries", response_model=list[PublicDictionaryOut])
def list_dictionaries(
    caller: ApiCaller = Depends(get_api_caller),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[PublicDictionaryOut]:
    _enforce_rate_limit(db, caller, settings)
    return query_service.list_public_dictionaries(db)
