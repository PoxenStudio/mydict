"""前台（网页端）按 IP 的每分钟限流：查询、词条文档、在线词典各自计数。

Token 的按日限流见 rate_limit_service。
"""

from sqlalchemy.orm import Session

from app.core import rate_limiter
from app.core.config import Settings
from app.core.deps import WebCaller
from app.core.exceptions import RateLimitedError
from app.services import query_log_service
from app.services.settings_service import get_int_setting

# 词条文档的每分钟限额 = 查询限额 × 这个倍数。一次查询之后要展开多部词典、用 ←/→ 来回
# 切换，每次都会取一次词条文档，所以给得比查询宽得多；但不能不限——否则它就成了绕过
# 查询配额的抓取入口。
_ENTRY_RATE_MULTIPLIER = 10

# 在线抓取比本地查询贵得多（出站 HTTP + 第三方站点的耐受度），限额收紧到按 IP
# 查询限额的一半。与词条文档的乘数做法相反——那里是放大（它是已计费查询的子
# 请求），这里是缩小（它是独立的出站行为）。
_ONLINE_RATE_DIVISOR = 2
_ONLINE_RATE_MIN = 5


def ip_rate_limit(db: Session, caller: WebCaller, settings: Settings) -> tuple[str, int]:
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


def enforce_query_limit(db: Session, caller: WebCaller, settings: Settings, word: str) -> None:
    """查询配额（/search、随机浏览共用）；超限记一条 rate_limited 查询日志。"""
    counter_key, limit = ip_rate_limit(db, caller, settings)
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


def enforce_entry_limit(db: Session, caller: WebCaller, settings: Settings) -> None:
    """词条文档单独计数，不占查询配额（见 _ENTRY_RATE_MULTIPLIER）。超限不写 query_logs：
    它不是一次查词，记进去会污染查询统计。"""
    counter_key, limit = ip_rate_limit(db, caller, settings)
    if not rate_limiter.check_and_increment(f"entry:{counter_key}", limit * _ENTRY_RATE_MULTIPLIER):
        raise RateLimitedError(
            "词条加载过于频繁，请稍后再试", retry_after=rate_limiter.seconds_to_next_minute()
        )


def enforce_online_limit(db: Session, caller: WebCaller, settings: Settings) -> None:
    """在线词典单独计数，不占查询配额（见 _ONLINE_RATE_DIVISOR）。"""
    counter_key, limit = ip_rate_limit(db, caller, settings)
    online_limit = max(_ONLINE_RATE_MIN, limit // _ONLINE_RATE_DIVISOR)
    if not rate_limiter.check_and_increment(f"online:{counter_key}", online_limit):
        raise RateLimitedError(
            "在线词典查询过于频繁，请稍后再试", retry_after=rate_limiter.seconds_to_next_minute()
        )
