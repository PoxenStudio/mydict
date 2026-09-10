from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Dictionary(Base):
    __tablename__ = "dictionaries"
    __table_args__ = (
        CheckConstraint("format IN ('mdict','stardict','ecdict')", name="ck_dictionaries_format"),
        CheckConstraint("status IN ('enabled','disabled')", name="ck_dictionaries_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    lang_from: Mapped[str] = mapped_column(String(8), nullable=False)
    lang_to: Mapped[str] = mapped_column(String(8), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(16), default="disabled", server_default="disabled")
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    imported_by: Mapped[int | None] = mapped_column(ForeignKey("admins.id"), nullable=True)


class DictEntry(Base):
    __tablename__ = "dict_entries"
    __table_args__ = (
        UniqueConstraint("dictionary_id", "word", name="uq_dict_entries_dictionary_word"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dictionary_id: Mapped[int] = mapped_column(
        ForeignKey("dictionaries.id", ondelete="CASCADE"), nullable=False
    )
    word: Mapped[str] = mapped_column(String(255), nullable=False)
    word_lower: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phonetic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    extra: Mapped[str | None] = mapped_column(Text, nullable=True)
