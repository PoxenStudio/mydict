"""dictionary spx scan

Revision ID: c8f1a2b3d4e5
Revises: 47433b054a08
Create Date: 2026-09-22 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8f1a2b3d4e5'
down_revision: Union[str, None] = '47433b054a08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 两列都只在后台线程里写（导入后检测 / 手动扫描 / 转码结束），列表接口不做实时扫描：
    # The little dict 单部就有 67.6 万个资源文件，63 部逐个走一遍会让列表请求卡死。
    # spx_scanned_at 为 NULL 表示「从未检测」，用来把「扫过、无需转码」与「还没扫过」区分开
    # ——这两种情况的 spx_pending_count 都是 0。
    with op.batch_alter_table("dictionaries") as batch_op:
        batch_op.add_column(
            sa.Column("spx_pending_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("spx_scanned_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("dictionaries") as batch_op:
        batch_op.drop_column("spx_scanned_at")
        batch_op.drop_column("spx_pending_count")
