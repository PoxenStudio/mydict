"""删掉服务端 Speex 转码遗留的 dictionaries.spx_pending_count / spx_scanned_at

转码方案已改为前端 JS 解码，这两列不再读写。它们在 dictionaries 上（几十行的小表），
删列没有成本；一并清掉已废弃的 spx_online_transcode 系统设置。

Revision ID: b4e6a8c0d2f4
Revises: a3d5f7b9c1e2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4e6a8c0d2f4"
down_revision: Union[str, None] = "a3d5f7b9c1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ("spx_pending_count", "spx_scanned_at")


def _supports_drop_column() -> bool:
    version = op.get_bind().exec_driver_sql("SELECT sqlite_version()").scalar_one()
    return tuple(int(part) for part in version.split(".")[:2]) >= (3, 35)


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("dictionaries")}
    targets = [name for name in _COLUMNS if name in existing]
    if _supports_drop_column():
        # 原生 DROP COLUMN 不重建表，也就不必动 dict_entries 指向它的外键
        for name in targets:
            op.execute(f"ALTER TABLE dictionaries DROP COLUMN {name}")
    elif targets:
        with op.batch_alter_table("dictionaries") as batch_op:
            for name in targets:
                batch_op.drop_column(name)
    op.execute("DELETE FROM system_settings WHERE key = 'spx_online_transcode'")


def downgrade() -> None:
    op.add_column(
        "dictionaries",
        sa.Column("spx_pending_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("dictionaries", sa.Column("spx_scanned_at", sa.DateTime(), nullable=True))
