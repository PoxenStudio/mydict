"""生词本引入 FSRS 复习调度

- 两张生词本表各加 5 列：fsrs_card（JSON 快照）、due_at（下次到期，带索引）、
  reps、lapses、last_review_at。已有数据全部视为「新词」（reps=0、due_at 为空）。
- 新增 vocab_reviews：一次复习一条流水，调度状态可由它重算；client_review_id
  用于多端离线补交的幂等去重。

Revision ID: b7d2f4a6c8e0
Revises: a4f7c2e9d1b3
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d2f4a6c8e0"
down_revision: Union[str, None] = "a4f7c2e9d1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("vocab_items", "token_vocab_items")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("fsrs_card", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("due_at", sa.DateTime(), nullable=True))
        op.add_column(
            table, sa.Column("reps", sa.Integer(), nullable=False, server_default="0")
        )
        op.add_column(
            table, sa.Column("lapses", sa.Integer(), nullable=False, server_default="0")
        )
        op.add_column(table, sa.Column("last_review_at", sa.DateTime(), nullable=True))
        op.create_index(f"ix_{table}_due_at", table, ["due_at"])

    op.create_table(
        "vocab_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_kind", sa.String(length=8), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("vocab_item_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.Column("prev_due_at", sa.DateTime(), nullable=True),
        sa.Column("next_due_at", sa.DateTime(), nullable=True),
        sa.Column("client", sa.String(length=16), nullable=True),
        sa.Column("client_review_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_vocab_reviews_client_id",
        "vocab_reviews",
        ["owner_kind", "owner_id", "client_review_id"],
        unique=True,
        sqlite_where=sa.text("client_review_id IS NOT NULL"),
    )
    op.create_index(
        "ix_vocab_reviews_owner_time",
        "vocab_reviews",
        ["owner_kind", "owner_id", "reviewed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_vocab_reviews_owner_time", table_name="vocab_reviews")
    op.drop_index("uq_vocab_reviews_client_id", table_name="vocab_reviews")
    op.drop_table("vocab_reviews")
    for table in _TABLES:
        op.drop_index(f"ix_{table}_due_at", table_name=table)
        op.drop_column(table, "last_review_at")
        op.drop_column(table, "lapses")
        op.drop_column(table, "reps")
        op.drop_column(table, "due_at")
        op.drop_column(table, "fsrs_card")
