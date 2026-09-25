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
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # 当前生效的词条「代」：查询只看 dict_entries.generation 等于它的行。重新解析把新词条
    # 写成下一代，写完只改这一列就完成切换（见 dictionary_service._reparse_one）
    active_generation: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
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
    # 与 dictionaries.active_generation 相等才对查询可见，读路径统一经过
    # entry_scope.current_generation_only 过滤
    generation: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

