"""同一部词典允许存在多条同名词条

MDict 允许同一词头有多条内容不同的条目（搜韵诗词全文检索版里「毛泽东」有 82 条，是 82 首
不同的诗词）。原先的 `UNIQUE(dictionary_id, word)` 让导入时只保留首条，在 63 部词典上静默
丢了 1,445,181 条内容——不报错、也不体现在 word_count 里（记的是去重后的行数）。

去掉约束后必须补一条 `(dictionary_id, word_lower)` 复合索引：查询就是按这两列过滤的，
而原来那条唯一索引建在 `(dictionary_id, word)` 上（word 不是 word_lower），对查询使不上力。

SQLite 上 `drop_constraint(type_="unique")` 会走 batch_alter_table 的整表重建——生产库
（29GB / 2470 万行）要预留停机时间。

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


def upgrade() -> None:
    # SQLite 的 DDL 按 alembic 的假设是非事务性的：batch_alter_table 的「建临时表」这一步
    # 会立即提交。所以上次运行若在拷数据途中被打断（进程被杀、断电），会留下一个空的
    # `_alembic_tmp_dict_entries`，重跑时直接撞「table already exists」。先清掉它，
    # 让迁移可以安全重试。
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_dict_entries")
    with op.batch_alter_table("dict_entries") as batch_op:
        batch_op.drop_constraint("uq_dict_entries_dictionary_word", type_="unique")
        batch_op.create_index(
            "ix_dict_entries_dict_word_lower", ["dictionary_id", "word_lower"], unique=False
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
