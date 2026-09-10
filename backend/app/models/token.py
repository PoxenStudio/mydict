from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, func
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
    # None 表示不限制，可查询全部已启用词典；非 None 时是词典 id 列表，查询按交集限定；
    # 用原生 JSON 列类型（ORM 层自动序列化成 Python list），不是别处那种手动 json.dumps
    # 的 TEXT 列，因为这里就是单纯的 id 列表，没有 detail/extra 那种自由结构需要透传。
    allowed_dictionary_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
