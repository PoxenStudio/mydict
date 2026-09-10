from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class QueryLog(Base):
    """查询原始明细，用于近期统计与排障；定期归档/清理，避免单表无限增长。"""

    __tablename__ = "query_logs"
    __table_args__ = (CheckConstraint("source IN ('api','web')", name="ck_query_logs_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    token_id: Mapped[int | None] = mapped_column(ForeignKey("api_tokens.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    word: Mapped[str] = mapped_column(String(255), nullable=False)
    dictionary_id: Mapped[int | None] = mapped_column(ForeignKey("dictionaries.id"), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class QueryStatsDaily(Base):
    """由定时任务从 query_logs 聚合落库，供统计页快速查询。"""

    __tablename__ = "query_stats_daily"
    __table_args__ = (
        UniqueConstraint("stat_date", "token_id", "user_id", name="uq_query_stats_daily_dim"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stat_date: Mapped[str] = mapped_column(String(10), nullable=False)
    token_id: Mapped[int | None] = mapped_column(ForeignKey("api_tokens.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    query_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rate_limited_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
