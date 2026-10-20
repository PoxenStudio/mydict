"""生词本：句子挖矿字段（上下文原句 + 来源）

收藏时可以顺带存「遇到这个词的那句话」，复习时用它做挖空提示。三端采集能力不同
（扩展能读 DOM、桌面只有剪贴板），所以全部可空；老数据保持 NULL，复习退回裸词卡。

Revision ID: c9e1f3a5b7d2
Revises: b7d2f4a6c8e0
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9e1f3a5b7d2"
down_revision: Union[str, None] = "b7d2f4a6c8e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("vocab_items", "token_vocab_items")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("context_sentence", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("context_match", sa.String(length=64), nullable=True))
        op.add_column(table, sa.Column("context_source", sa.String(length=255), nullable=True))
        op.add_column(table, sa.Column("context_url", sa.Text(), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "context_url")
        op.drop_column(table, "context_source")
        op.drop_column(table, "context_match")
        op.drop_column(table, "context_sentence")
