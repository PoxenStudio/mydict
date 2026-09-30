from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


# 生词本是「词条级」的：同一部词典同一个词只留一条，不同词典之间互不冲突
# （中文词典的「人気」和 NHK 的「人気」价值不同，都该能收藏）。
#
# SQLite 的唯一索引把 NULL 视作互不相等，所以 dictionary_id 为 NULL 的那批
# （历史数据、手工调 API 未带词典、词典被删后）用不上索引，重复由服务层兜住；
# 部分索引 `WHERE dictionary_id IS NOT NULL` 覆盖真正需要约束的那部分。
class VocabItem(Base):
    """网页端用户生词本；phonetic/definition 为收藏时的释义快照。"""

    __tablename__ = "vocab_items"
    __table_args__ = (
        Index(
            "uq_vocab_items_user_dict_word",
            "user_id",
            "dictionary_id",
            "word",
            unique=True,
            sqlite_where=text("dictionary_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    word: Mapped[str] = mapped_column(String(255), nullable=False)
    dictionary_id: Mapped[int | None] = mapped_column(ForeignKey("dictionaries.id"), nullable=True)
    # 词典名字快照：词典被删后（dictionary_id 置 NULL）列表仍要显示来源
    dictionary_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phonetic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TokenVocabItem(Base):
    """Token 独立生词本，与 users/vocab_items 完全独立，仅归属发起调用的 Token。"""

    __tablename__ = "token_vocab_items"
    __table_args__ = (
        Index(
            "uq_token_vocab_items_token_dict_word",
            "token_id",
            "dictionary_id",
            "word",
            unique=True,
            sqlite_where=text("dictionary_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    token_id: Mapped[int] = mapped_column(
        ForeignKey("api_tokens.id", ondelete="CASCADE"), nullable=False
    )
    word: Mapped[str] = mapped_column(String(255), nullable=False)
    dictionary_id: Mapped[int | None] = mapped_column(ForeignKey("dictionaries.id"), nullable=True)
    dictionary_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phonetic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
