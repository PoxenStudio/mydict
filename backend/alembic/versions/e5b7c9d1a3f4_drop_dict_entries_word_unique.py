"""同一部词典允许存在多条同名词条

MDict 允许同一词头有多条内容不同的条目（搜韵诗词全文检索版里「毛泽东」有 82 条，是 82 首
不同的诗词）。原先的 `UNIQUE(dictionary_id, word)` 让导入时只保留首条，在 63 部词典上静默
丢了 1,445,181 条内容——不报错、也不体现在 word_count 里（记的是去重后的行数）。

去掉约束后必须补一条 `(dictionary_id, word_lower)` 复合索引：查询就是按这两列过滤的，
而原来那条唯一索引建在 `(dictionary_id, word)` 上（word 不是 word_lower），对查询使不上力。

SQLite 上 `drop_constraint(type_="unique")` 会走 batch_alter_table 的整表重建——生产库
（29GB / 2470 万行）要跑几十分钟、需要同等大小的剩余磁盘，所以标记为重型迁移：启动时
先检查磁盘空间再执行。

Revision ID: e5b7c9d1a3f4
Revises: c8f1a2b3d4e5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5b7c9d1a3f4"
down_revision: Union[str, None] = "c8f1a2b3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

heavy = True

_TMP_TABLE = "_alembic_tmp_dict_entries"
_UNIQUE_NAME = "uq_dict_entries_dictionary_word"


def upgrade() -> None:
    """可在任意中断点之后安全重跑。

    alembic 把 SQLite 的 DDL 当作非事务性的，batch 重建的每一步（建临时表 → 拷数据 →
    删原表 → 临时表改名 → 建索引）都可能单独落盘。上次若在中途被打断，按现场分情况收拾：

    - 原表还在：临时表只是半成品，删掉重来；
    - 原表已删、临时表还在：说明拷贝已经完成（删原表在拷贝之后），数据全在临时表里——
      **绝不能删它**，改名回来即可；
    - 约束已经没了：重建那一步做完了，只需补齐索引。
    """
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "dict_entries" not in tables:
        if _TMP_TABLE not in tables:
            raise RuntimeError("dict_entries 与临时表都不存在，数据库状态异常，请从备份恢复")
        op.rename_table(_TMP_TABLE, "dict_entries")
    elif _TMP_TABLE in tables:
        op.drop_table(_TMP_TABLE)

    uniques = {item["name"] for item in sa.inspect(bind).get_unique_constraints("dict_entries")}
    if _UNIQUE_NAME in uniques:
        with op.batch_alter_table("dict_entries") as batch_op:
            batch_op.drop_constraint(_UNIQUE_NAME, type_="unique")
    # 改名回来的临时表没有索引（batch 在改名之后才建），两条都要按需补上
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dict_entries_word_lower ON dict_entries (word_lower)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dict_entries_dict_word_lower "
        "ON dict_entries (dictionary_id, word_lower)"
    )


def downgrade() -> None:
    """回退时要重新加回唯一约束——若库里已经存在同名词条，这一步会失败。

    这是刻意的：降级的正确做法是先把重复条目处理掉，而不是让约束静默吞掉数据。
    """
    connection = op.get_bind()
    duplicates = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM ("
            "  SELECT dictionary_id, word FROM dict_entries"
            "  GROUP BY dictionary_id, word HAVING COUNT(*) > 1"
            ")"
        )
    ).scalar()
    if duplicates:
        raise RuntimeError(
            f"库里有 {duplicates} 组同名词条，无法恢复唯一约束；请先处理掉重复条目再降级"
        )
    with op.batch_alter_table("dict_entries") as batch_op:
        batch_op.drop_index("ix_dict_entries_dict_word_lower")
        batch_op.create_unique_constraint(
            "uq_dict_entries_dictionary_word", ["dictionary_id", "word"]
        )
