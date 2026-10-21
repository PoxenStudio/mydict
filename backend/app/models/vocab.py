from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class VocabContextMixin:
    """句子挖矿：收藏时顺手存下「你遇到它的那句话」以及来源。

    三端采集能力不同（扩展能读 DOM，桌面只有剪贴板），所以全部可空；
    复习时没有句子就退回裸词卡。`context_match` 记录句子里实际出现的那个词形
    （可能是 banks/banked），挖空时按它精确替换，找不到再用 word 做词尾回退。
    """

    context_sentence: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_match: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    context_url: Mapped[str | None] = mapped_column(Text, nullable=True)


class VocabSrsMixin:
    """生词本的复习调度状态（FSRS）。

    FSRS 的卡片状态整体放在 `fsrs_card`（库自带的 JSON），其余列是为了查询/展示
    才镜像出来的：`due_at` 支持索引排序，`reps/lapses` 用来区分新词和已学词。
    调度算法只由 vocab_srs_service 读写，别在别处解释这些字段。
    """

    fsrs_card: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    reps: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    lapses: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# 生词本是「词条级」的：同一部词典同一个词只留一条，不同词典之间互不冲突
# （中文词典的「人気」和 NHK 的「人気」价值不同，都该能收藏）。
#
# SQLite 的唯一索引把 NULL 视作互不相等，所以 dictionary_id 为 NULL 的那批
# （历史数据、手工调 API 未带词典、词典被删后）用不上索引，重复由服务层兜住；
# 部分索引 `WHERE dictionary_id IS NOT NULL` 覆盖真正需要约束的那部分。
class VocabItem(VocabContextMixin, VocabSrsMixin, Base):
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


class TokenVocabItem(VocabContextMixin, VocabSrsMixin, Base):
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


class VocabReview(Base):
    """一次复习的流水（事实来源）。

    调度状态是派生值，真正的历史留在这里：以后换算法、调 FSRS 参数、做统计
    都靠它。`client_review_id` 用于多端补交时幂等——离线队列重发不会重复计一次。
    """

    __tablename__ = "vocab_reviews"
    __table_args__ = (
        Index(
            "uq_vocab_reviews_client_id",
            "owner_kind",
            "owner_id",
            "client_review_id",
            unique=True,
            sqlite_where=text("client_review_id IS NOT NULL"),
        ),
        Index("ix_vocab_reviews_owner_time", "owner_kind", "owner_id", "reviewed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # user / token：与两张生词本表对应，故不加外键（跨表引用）
    owner_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    vocab_item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 1=Again 2=Hard 3=Good 4=Easy（与 FSRS Rating 一致）
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    prev_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # desktop / android / extension / web，便于以后看各端使用情况
    client: Mapped[str | None] = mapped_column(String(16), nullable=True)
    client_review_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
