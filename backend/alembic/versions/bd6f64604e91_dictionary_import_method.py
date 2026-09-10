"""dictionary import method

Revision ID: bd6f64604e91
Revises: df2e34e6bb5e
Create Date: 2026-09-10 19:48:32.546084

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd6f64604e91'
down_revision: Union[str, None] = 'df2e34e6bb5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 已存在的记录一律标成 dicts_dir（删除时不动 source/），比默认按 upload 处理更保守，
    # 不会在升级后意外删掉迁移前导入的原始文件。
    with op.batch_alter_table("dictionaries") as batch_op:
        batch_op.add_column(
            sa.Column(
                "import_method",
                sa.String(16),
                nullable=False,
                server_default="dicts_dir",
            )
        )
        batch_op.create_check_constraint(
            "ck_dictionaries_import_method", "import_method IN ('upload','dicts_dir')"
        )


def downgrade() -> None:
    with op.batch_alter_table("dictionaries") as batch_op:
        batch_op.drop_constraint("ck_dictionaries_import_method", type_="check")
        batch_op.drop_column("import_method")
