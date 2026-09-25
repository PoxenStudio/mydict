"""重新解析的暂存表 dict_entries_staging

已被 a3d5f7b9c1e2（词条「代」方案）取代并删除，保留本迁移只为让版本链连续。

Revision ID: f2c4d6e8a0b1
Revises: e5b7c9d1a3f4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2c4d6e8a0b1"
down_revision: Union[str, None] = "e5b7c9d1a3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_index("ix_dict_entries_staging_dict_id", table_name="dict_entries_staging")
    op.drop_table("dict_entries_staging")
