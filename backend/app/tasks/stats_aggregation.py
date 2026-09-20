"""把 query_logs 聚合进 query_stats_daily 的「用户」与「匿名」维度。

Token 维度的 query_count/rate_limited_count 已在限流环节实时写入该表（见
services/rate_limit_service.py），这里跳过 token_id 非空的日志，避免重复统计、
与实时计数打架；只处理匿名调用（token_id 和 user_id 均为空）与登录用户调用。
"""

from datetime import date

from app.core.db import SessionLocal
from app.core.timeutil import day_bounds_utc
from app.models.query import QueryLog, QueryStatsDaily


def _upsert(
    db, stat_date: str, user_id: int | None, query_count: int, rate_limited_count: int
) -> None:
    query = db.query(QueryStatsDaily).filter(
        QueryStatsDaily.stat_date == stat_date, QueryStatsDaily.token_id.is_(None)
    )
    query = query.filter(
        QueryStatsDaily.user_id.is_(None) if user_id is None else QueryStatsDaily.user_id == user_id
    )
    row = query.first()
    if row is None:
        db.add(
            QueryStatsDaily(
                stat_date=stat_date,
                token_id=None,
                user_id=user_id,
                query_count=query_count,
                rate_limited_count=rate_limited_count,
            )
        )
    else:
        row.query_count = query_count
        row.rate_limited_count = rate_limited_count


def aggregate_date(target_date: str) -> None:
    db = SessionLocal()
    try:
        # 按「本地日」的 UTC 区间取日志，与写进 stat_date 的本地日期标签口径一致——之前用
        # func.date(created_at) 是按 UTC 日分组，与本地日标签错开一个时区偏移。
        day_start, day_end = day_bounds_utc(date.fromisoformat(target_date))
        logs = (
            db.query(QueryLog)
            .filter(
                QueryLog.created_at >= day_start,
                QueryLog.created_at < day_end,
                QueryLog.token_id.is_(None),
            )
            .all()
        )
        user_buckets: dict[int, list[int]] = {}
        anon_bucket = [0, 0]
        for log in logs:
            bucket = user_buckets.setdefault(log.user_id, [0, 0]) if log.user_id else anon_bucket
            if log.status == "rate_limited":
                bucket[1] += 1
            else:
                bucket[0] += 1

        for user_id, (query_count, rate_limited_count) in user_buckets.items():
            _upsert(db, target_date, user_id, query_count, rate_limited_count)
        _upsert(db, target_date, None, anon_bucket[0], anon_bucket[1])
        db.commit()
    finally:
        db.close()
