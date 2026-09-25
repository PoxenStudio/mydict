"""词条「代」：dict_entries.generation + dictionaries.active_generation

重新解析把新词条写成下一代，写完只改 dictionaries.active_generation 一行即完成切换，
旧一代随后分批删除。

两列都用 ALTER TABLE ADD COLUMN（常量默认值），SQLite 只改表定义、不重建表，
在 29GB 的生产库上也是瞬时完成。刻意不用 batch_alter_table——那会整表重建。
存量行 generation=0、active_generation=0，全部可见。

同时删掉上一版方案的暂存表 dict_entries_staging（f2c4d6e8a0b1）。

Revision ID: a3d5f7b9c1e2
Revises: f2c4d6e8a0b1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3d5f7b9c1e2"
down_revision: Union[str, None] = "f2c4d6e8a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_dict_entries_staging_dict_id", table_name="dict_entries_staging")
    op.drop_table("dict_entries_staging")
    op.add_column(
        "dictionaries",
        sa.Column("active_generation", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "dict_entries",
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    # 降级后查询不再区分代：先删掉非当前代的行，免得它们变成重复结果
    op.execute(
        "DELETE FROM dict_entries WHERE generation != ("
        "  SELECT active_generation FROM dictionaries"
        "  WHERE dictionaries.id = dict_entries.dictionary_id)"
    )
    with op.batch_alter_table("dict_entries") as batch_op:
        batch_op.drop_column("generation")
    with op.batch_alter_table("dictionaries") as batch_op:
        batch_op.drop_column("active_generation")
    op.create_table(
        "dict_entries_staging",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dictionary_id", sa.Integer(), nullable=False),
        sa.Column("word", sa.String(length=255), nullable=False),
        sa.Column("word_lower", sa.String(length=255), nullable=False),
        sa.Column("phonetic", sa.String(length=255), nullable=True),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("extra", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_dict_entries_staging_dict_id", "dict_entries_staging", ["dictionary_id", "id"]
    )
