from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("status IN ('active','disabled')", name="ck_users_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # None 表示不限制，可查询全部已启用词典；非 None 时是词典 id 列表，用户自己在
    # 前台「词典选择」里设置，查询按交集限定。
    allowed_dictionary_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
