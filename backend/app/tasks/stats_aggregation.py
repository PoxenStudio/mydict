"""把 query_logs 聚合进 query_stats_daily 的「用户」与「匿名」维度。

Token 维度的 query_count/rate_limited_count 已在限流环节实时写入该表（见
services/rate_limit_service.py），这里跳过 token_id 非空的日志，避免重复统计、
与实时计数打架；只处理匿名调用（token_id 和 user_id 均为空）与登录用户调用。
"""

from sqlalchemy import func

from app.core.db import SessionLocal
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
        logs = (
            db.query(QueryLog)
            .filter(func.date(QueryLog.created_at) == target_date, QueryLog.token_id.is_(None))
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
