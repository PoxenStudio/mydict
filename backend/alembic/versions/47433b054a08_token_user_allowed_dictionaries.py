"""token user allowed dictionaries

Revision ID: 47433b054a08
Revises: bd6f64604e91
Create Date: 2026-09-10 21:46:34.133973

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '47433b054a08'
down_revision: Union[str, None] = 'bd6f64604e91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NULL = 不限制，可查询全部已启用词典；非 NULL 时是词典 id 的 JSON 数组，
    # 查询时与已启用词典求交集。
    with op.batch_alter_table("api_tokens") as batch_op:
        batch_op.add_column(sa.Column("allowed_dictionary_ids", sa.JSON(), nullable=True))
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("allowed_dictionary_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("allowed_dictionary_ids")
    with op.batch_alter_table("api_tokens") as batch_op:
        batch_op.drop_column("allowed_dictionary_ids")
