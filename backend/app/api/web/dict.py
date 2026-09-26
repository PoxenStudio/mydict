import time
from pathlib import Path
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
from app.schemas.query import PublicDictionaryOut, QueryHistoryResponse, WebQueryResponse
from app.services import query_log_service, query_service, resource_service
from app.services.entry_render_service import render_entries_document
from app.services.settings_service import get_int_setting

router = APIRouter(prefix="/dict", tags=["web-dict"])

# 词条文档的每分钟限额 = 查询限额 × 这个倍数。一次查询之后要展开多部词典、用 ←/→ 来回
# 切换，每次都会取一次词条文档，所以给得比查询宽得多；但不能不限——否则它就成了绕过
# 查询配额的抓取入口。
_ENTRY_RATE_MULTIPLIER = 10


def _ip_rate_limit(db: Session, caller: WebCaller, settings: Settings) -> tuple[str, int]:
    """返回 (计数 key, 每分钟限额)。

    访客与匿名 API 调用共用同一套按 IP 限流规则；登录用户走单独的（通常更宽松的）按 IP
    限流阈值。计数 key 按登录态区分前缀，避免同一 IP 下匿名与登录用户互相挤占对方的配额。
    """
    ip = caller.ip or "unknown"
    if caller.user is None:
        limit = get_int_setting(
            db, "anonymous_ip_rate_limit_per_min", settings.anonymous_ip_rate_limit_per_min
        )
        return f"anon:{ip}", limit
    limit = get_int_setting(db, "user_ip_rate_limit_per_min", settings.user_ip_rate_limit_per_min)
    return f"user:{ip}", limit


def _enforce_web_rate_limit(db: Session, caller: WebCaller, settings: Settings, word: str) -> None:
    counter_key, limit = _ip_rate_limit(db, caller, settings)
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
def list_dictionaries(
    scope: Literal["usable", "all"] = "usable",
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[PublicDictionaryOut]:
    """`usable`（默认）：当前用户能用的词典，即已启用词典与其「可用词典」设置的交集，供首页
    「检索范围」面板。`all`：全部已启用词典，供「词典选择」弹窗——那是用来配置限制的，
    被限制过滤了就没法再选回来。"""
    allowed_ids = user.allowed_dictionary_ids if scope == "usable" else None
    return query_service.list_public_dictionaries(db, allowed_ids)


@router.get("/search", response_model=WebQueryResponse)
def search(
    word: str,
    dict: str | None = None,  # noqa: A002 - 与 API 契约中的查询参数名保持一致
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    caller: WebCaller = Depends(get_web_caller),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WebQueryResponse:
    _enforce_web_rate_limit(db, caller, settings, word)

    allowed_ids = caller.user.allowed_dictionary_ids if caller.user else None
    started = time.perf_counter()
    results = query_service.search_word(
        db,
        word,
        query_service.parse_dict_ids(dict),
        from_,
        to,
        allowed_ids,
        include_definitions=False,
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
    return WebQueryResponse(results=results)


def _enforce_entry_rate_limit(db: Session, caller: WebCaller, settings: Settings) -> None:
    """词条文档单独计数，不占查询配额（见 _ENTRY_RATE_MULTIPLIER）。超限不写 query_logs：
    它不是一次查词，记进去会污染查询统计。"""
    counter_key, limit = _ip_rate_limit(db, caller, settings)
    if not rate_limiter.check_and_increment(f"entry:{counter_key}", limit * _ENTRY_RATE_MULTIPLIER):
        raise RateLimitedError(
            "词条加载过于频繁，请稍后再试", retry_after=rate_limiter.seconds_to_next_minute()
        )


def _parse_entry_ids(raw: str | None) -> list[int] | None:
    """把 `?entry_ids=12,34,56` 解析成 id 列表；空/非法时返回 None（走按词的路径）。

    上限 200：一个词头的同名词条再多也不会超过这个数（实测最多 82），超了说明请求被伪造，
    按 None 处理走按词路径即可。
    """
    if not raw:
        return None
    try:
        ids = [int(part) for part in raw.split(",") if part.strip()]
    except ValueError:
        return None
    ids = sorted({i for i in ids if i > 0})
    return ids[:200] or None


@router.get("/entry/{dictionary_id}", response_class=HTMLResponse)
def entry_document(
    dictionary_id: int,
    word: str,
    entry_ids: str | None = None,
    theme: Literal["light", "dark"] | None = None,
    caller: WebCaller = Depends(get_web_caller),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """把单条词条的释义渲染成独立 HTML 文档，供前端放进隔离 iframe。

    前端用 axios 带 token 取回内容后塞进 srcdoc，而不是让 iframe 直接导航到这里：
    iframe 导航不会带 Authorization 头，端点就只能匿名开放，会绕过 Token 的
    「可用词典」限制。

    不计入按 IP 的**查询**配额：它是一次已经计过配额的查询的子请求，按部计费会让
    「展开 N 部词典」变成 N+1 次配额。但它有自己的、宽得多的按 IP 限额，否则就成了绕过
    查询配额的抓取入口。

    `word` 必须是用户查询时输入的那个词：`entry_ids` 只在 `expand_word(word)` 的变体范围内
    生效——与 /search 的匹配范围完全一致，所以正常请求不受影响，而伪造的 id 取不到别的词条。

    theme 由前端按当前主题带上：直接写进文档，iframe 首屏就是正确的明暗，不必等父页的
    postMessage 到达再变色（那会有一次肉眼可见的闪变）。
    """
    _enforce_entry_rate_limit(db, caller, settings)

    dictionary = db.get(Dictionary, dictionary_id)
    allowed_ids = caller.user.allowed_dictionary_ids if caller.user else None
    if (
        dictionary is None
        or dictionary.status != "enabled"
        or (allowed_ids and dictionary_id not in allowed_ids)
    ):
        # 未启用 / 不在授权范围内 / 不存在，统一 404，不泄漏词典是否存在
        raise NotFoundError("词条不存在")

    # 同一部词典里同一词头可以有多条内容不同的条目（MDict 允许），合成一个文档只要一个
    # iframe——逐条各建一个的话，搜韵这类词典展开一次就要挂载 82 个沙箱文档。
    # 前端把查询结果里这一组的条目 id 显式传过来，保证 iframe 里的条数与「共 N 条」一致
    # （按 word 再推一遍变体集合可能对不上）；没传就走按词的旧路径（兼容 / 单条）。
    entries = query_service.get_entries_for_document(
        db, dictionary_id, word, entry_ids=_parse_entry_ids(entry_ids)
    )
    if not entries:
        raise NotFoundError("词条不存在")

    return HTMLResponse(
        render_entries_document(
            # allow_lookup：只有前台查询页有查词框能接住「选中文字查词」这个动作
            [(e.word, e.definition, e.phonetic) for e in entries],
            dictionary_id=dictionary_id,
            theme=theme,
            allow_lookup=True,
            # mdx 同名的 .css/.js（MDict 客户端与 django-mdict 都会自动加载的那类）
            extra_head_assets=resource_service.same_name_assets(
                Path(settings.dictionary_storage_path) / str(dictionary_id) / "res",
                dictionary_id,
                dictionary.file_path,
            ),
        )
    )


@router.get("/history", response_model=QueryHistoryResponse)
def history(
    user: User = Depends(require_user), db: Session = Depends(get_db)
) -> QueryHistoryResponse:
    return QueryHistoryResponse(items=query_log_service.get_recent_history(db, user.id, 100))
