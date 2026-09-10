from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ApiToken(Base):
    __tablename__ = "api_tokens"
    __table_args__ = (
        CheckConstraint("status IN ('active','disabled')", name="ck_api_tokens_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    daily_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admins.id"), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
