from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class VocabItem(Base):
    """网页端用户生词本；phonetic/definition 为收藏时的释义快照。"""

    __tablename__ = "vocab_items"
    __table_args__ = (UniqueConstraint("user_id", "word", name="uq_vocab_items_user_word"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    word: Mapped[str] = mapped_column(String(255), nullable=False)
    dictionary_id: Mapped[int | None] = mapped_column(ForeignKey("dictionaries.id"), nullable=True)
    phonetic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TokenVocabItem(Base):
    """Token 独立生词本，与 users/vocab_items 完全独立，仅归属发起调用的 Token。"""

    __tablename__ = "token_vocab_items"
    __table_args__ = (UniqueConstraint("token_id", "word", name="uq_token_vocab_items_token_word"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    token_id: Mapped[int] = mapped_column(
        ForeignKey("api_tokens.id", ondelete="CASCADE"), nullable=False
    )
    word: Mapped[str] = mapped_column(String(255), nullable=False)
    dictionary_id: Mapped[int | None] = mapped_column(ForeignKey("dictionaries.id"), nullable=True)
    phonetic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
