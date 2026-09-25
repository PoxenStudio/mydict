from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Dictionary(Base):
    __tablename__ = "dictionaries"
    __table_args__ = (
        CheckConstraint("format IN ('mdict','stardict','ecdict')", name="ck_dictionaries_format"),
        CheckConstraint("status IN ('enabled','disabled')", name="ck_dictionaries_status"),
        CheckConstraint(
            "import_method IN ('upload','dicts_dir')", name="ck_dictionaries_import_method"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    lang_from: Mapped[str] = mapped_column(String(8), nullable=False)
    lang_to: Mapped[str] = mapped_column(String(8), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    # upload：浏览器上传，源文件由本应用暂存归档，删除词典时一并清理；
    # dicts_dir：从 /data/dicts 导入，源文件是用户自己放进去的，不移动、不代删。
    import_method: Mapped[str] = mapped_column(
        String(16), default="dicts_dir", server_default="dicts_dir"
    )
    word_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # 待转码的 .spx 发音数：同名同目录下没有非空 .mp3/.opus 产物的那些。
    # 刻意不做实时扫描——The little dict 单部就有 67.6 万个资源文件，63 部逐个走一遍会让
    # 列表接口卡死；改由「导入后检测 / 页面扫描发音资源 / 转码结束」三个时机写入。
    spx_pending_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # 上次检测时间；NULL 表示从未检测（存量数据）。用来把「扫过、无需转码」和「还没扫过」
    # 区分开——这两种情况的 spx_pending_count 都是 0。
    spx_scanned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(16), default="disabled", server_default="disabled")
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    imported_by: Mapped[int | None] = mapped_column(ForeignKey("admins.id"), nullable=True)


class DictEntry(Base):
    """一部词典里的词条。

    **同一部词典里允许存在多条同名词条**。MDict 就允许这样（搜韵诗词全文检索版里「毛泽东」
    有 82 条，是 82 首不同的诗词）；早先按 `UNIQUE(dictionary_id, word)` 建表，导入时同名的
    只留首条，于是在 63 部词典上静默丢了 1,445,181 条内容。

    查询按 `dictionary_id` + `word_lower` 过滤，所以去掉唯一约束后要补一条复合索引顶上——
    原来那条唯一索引建在 `(dictionary_id, word)` 上，用的是 word 而不是 word_lower，
    对查询本来就使不上力。
    """

    __tablename__ = "dict_entries"
    __table_args__ = (
        Index("ix_dict_entries_dict_word_lower", "dictionary_id", "word_lower"),
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


class DictEntryStaging(Base):
    """「重新解析」的暂存区：新词条先分批写到这里，写完再换进 `dict_entries`。

    直接在 `dict_entries` 上「先删后灌」会让这部词典在整个解析期间查不到内容，而且灌库
    的大事务长时间独占 SQLite 的写锁，站内每次查询都要写的 query_log 会因此超时报错。
    暂存区不参与查询，可以每批提交；只有最后的换入要碰正式表，且同样分批。
    """

    __tablename__ = "dict_entries_staging"
    __table_args__ = (Index("ix_dict_entries_staging_dict_id", "dictionary_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # 不加外键：解析中途词典被删时，残留行由下一次重新解析清掉即可
    dictionary_id: Mapped[int] = mapped_column(Integer, nullable=False)
    word: Mapped[str] = mapped_column(String(255), nullable=False)
    word_lower: Mapped[str] = mapped_column(String(255), nullable=False)
    phonetic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    extra: Mapped[str | None] = mapped_column(Text, nullable=True)
