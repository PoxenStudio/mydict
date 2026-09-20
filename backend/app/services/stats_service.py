from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationAppError
from app.core.timeutil import day, day_bounds_utc, parse_day, range_bounds_utc, today
from app.models.dictionary import Dictionary
from app.models.query import QueryLog, QueryStatsDaily
from app.models.token import ApiToken
from app.models.user import User

_VALID_DIMENSIONS = {"token", "user", "date", "source"}


def get_overview(db: Session) -> dict:
    # created_at 存的是 UTC，而「今天」按部署本地时区划分，所以必须用该本地日对应的 UTC 区间
    # 去比；拿本地日期直接和 func.date(created_at) 比会在本地 00:00 到 UTC 偏移之间错开一整天。
    start, end = day_bounds_utc(today())
    # 直接数 query_logs（而非等定时聚合写入 query_stats_daily），保证 Dashboard 概览实时；
    # 也更贴合「查询量」本身的语义——只数真正查过的词，不含 suggest/dictionaries 这类元信息调用。
    today_query_count = (
        db.query(func.count(QueryLog.id))
        .filter(
            QueryLog.created_at >= start,
            QueryLog.created_at < end,
            QueryLog.status != "rate_limited",
        )
        .scalar()
    )
    active_tokens = (
        db.query(func.count(func.distinct(QueryLog.token_id)))
        .filter(
            QueryLog.created_at >= start,
            QueryLog.created_at < end,
            QueryLog.token_id.isnot(None),
        )
        .scalar()
    )
    active_users = (
        db.query(func.count(func.distinct(QueryLog.user_id)))
        .filter(
            QueryLog.created_at >= start,
            QueryLog.created_at < end,
            QueryLog.user_id.isnot(None),
        )
        .scalar()
    )
    dictionary_count = db.query(func.count(Dictionary.id)).scalar()
    return {
        "today_query_count": int(today_query_count or 0),
        "active_tokens": int(active_tokens or 0),
        "active_users": int(active_users or 0),
        "dictionary_count": int(dictionary_count or 0),
    }


def _default_range(start_date: str | None, end_date: str | None) -> tuple[date, date] | None:
    """日期参数缺省取近 7 天；给了但格式非法返回 None，调用方按「查不到数据」处理。"""
    if (start_date and parse_day(start_date) is None) or (end_date and parse_day(end_date) is None):
        return None
    return parse_day(start_date) or day(-6), parse_day(end_date) or today()


def query_dimension_stats(
    db: Session, dimension: str, start_date: str | None, end_date: str | None
) -> list[dict]:
    if dimension not in _VALID_DIMENSIONS:
        raise ValidationAppError(f"不支持的统计维度：{dimension}")
    date_range = _default_range(start_date, end_date)
    if date_range is None:
        return []
    start, end = date_range

    if dimension == "token":
        rows = (
            db.query(
                ApiToken.id,
                ApiToken.name,
                func.coalesce(func.sum(QueryStatsDaily.query_count), 0),
                func.coalesce(func.sum(QueryStatsDaily.rate_limited_count), 0),
            )
            .join(
                QueryStatsDaily,
                (QueryStatsDaily.token_id == ApiToken.id)
                & (QueryStatsDaily.stat_date >= start.isoformat())
                & (QueryStatsDaily.stat_date <= end.isoformat()),
                isouter=True,
            )
            .group_by(ApiToken.id, ApiToken.name)
            .order_by(func.coalesce(func.sum(QueryStatsDaily.query_count), 0).desc())
            .all()
        )
        return [
            {"id": i, "label": name, "query_count": int(q), "rate_limited_count": int(r)}
            for i, name, q, r in rows
        ]

    if dimension == "user":
        rows = (
            db.query(
                User.id,
                User.username,
                func.coalesce(func.sum(QueryStatsDaily.query_count), 0),
                func.coalesce(func.sum(QueryStatsDaily.rate_limited_count), 0),
            )
            .join(
                QueryStatsDaily,
                (QueryStatsDaily.user_id == User.id)
                & (QueryStatsDaily.stat_date >= start.isoformat())
                & (QueryStatsDaily.stat_date <= end.isoformat()),
                isouter=True,
            )
            .group_by(User.id, User.username)
            .order_by(func.coalesce(func.sum(QueryStatsDaily.query_count), 0).desc())
            .all()
        )
        return [
            {"id": i, "label": name, "query_count": int(q), "rate_limited_count": int(r)}
            for i, name, q, r in rows
        ]

    if dimension == "date":
        rows = (
            db.query(
                QueryStatsDaily.stat_date,
                func.sum(QueryStatsDaily.query_count),
                func.sum(QueryStatsDaily.rate_limited_count),
            )
            .filter(QueryStatsDaily.stat_date >= start.isoformat(), QueryStatsDaily.stat_date <= end.isoformat())
            .group_by(QueryStatsDaily.stat_date)
            .order_by(QueryStatsDaily.stat_date)
            .all()
        )
        return [
            {"id": None, "label": d, "query_count": int(q), "rate_limited_count": int(r)}
            for d, q, r in rows
        ]

    # dimension == "source"：query_stats_daily 不含来源维度，直接从 query_logs 聚合
    range_start, range_end = range_bounds_utc(start, end)
    rows = (
        db.query(
            QueryLog.source,
            func.count(QueryLog.id).filter(QueryLog.status != "rate_limited"),
            func.count(QueryLog.id).filter(QueryLog.status == "rate_limited"),
        )
        .filter(QueryLog.created_at >= range_start, QueryLog.created_at < range_end)
        .group_by(QueryLog.source)
        .all()
    )
    return [
        {"id": None, "label": source, "query_count": int(q), "rate_limited_count": int(r)}
        for source, q, r in rows
    ]


def top_words(
    db: Session, start_date: str | None, end_date: str | None, limit: int = 10
) -> list[dict]:
    date_range = _default_range(start_date, end_date)
    if date_range is None:
        return []
    range_start, range_end = range_bounds_utc(*date_range)
    rows = (
        db.query(QueryLog.word, func.count(QueryLog.id))
        .filter(
            QueryLog.created_at >= range_start,
            QueryLog.created_at < range_end,
            QueryLog.status != "rate_limited",
        )
        .group_by(QueryLog.word)
        .order_by(func.count(QueryLog.id).desc())
        .limit(limit)
        .all()
    )
    return [{"word": w, "count": int(c)} for w, c in rows]
