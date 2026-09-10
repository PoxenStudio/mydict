"""Token 每日限流：直接以 query_stats_daily 当日行的 query_count 作为计数器。

按日限流天然需要跨进程重启保留状态，用 DB 行本身当计数器比另外维护一份内存态
再异步回写更简单可靠——写一次即是持久化，重启后读到的就是最新值，无需预加载。
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.query import QueryStatsDaily
from app.models.token import ApiToken


def _today() -> str:
    return date.today().isoformat()


def seconds_to_tomorrow() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((tomorrow - now).total_seconds())


def check_and_increment_token_daily(db: Session, token: ApiToken, default_daily_limit: int) -> bool:
    """返回 True 表示放行并已计数；False 表示本次请求已超限（不计入成功量，仅记超限次数）。"""
    limit = token.daily_limit if token.daily_limit is not None else default_daily_limit
    today = _today()
    row = (
        db.query(QueryStatsDaily)
        .filter(
            QueryStatsDaily.stat_date == today,
            QueryStatsDaily.token_id == token.id,
            QueryStatsDaily.user_id.is_(None),
        )
        .first()
    )
    current = row.query_count if row else 0
    if current >= limit:
        if row is None:
            row = QueryStatsDaily(stat_date=today, token_id=token.id, rate_limited_count=1)
            db.add(row)
        else:
            row.rate_limited_count += 1
        db.commit()
        return False

    if row is None:
        row = QueryStatsDaily(stat_date=today, token_id=token.id, query_count=1)
        db.add(row)
    else:
        row.query_count = current + 1
    db.commit()
    return True
