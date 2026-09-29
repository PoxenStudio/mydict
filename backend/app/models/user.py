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
    # 两列都是 None 表示不限制、非 None 时是词典 id 列表，实际生效的是两者的交集。
    # admin_ 那列是管理员在「用户管理」里划定的上限，用户自己改不了；另一列是用户在
    # 前台「词典选择」里的自选，只能在上限之内挑。
    admin_allowed_dictionary_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    allowed_dictionary_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
