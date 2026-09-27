"""api_tokens 关联用户：user_id（每个用户至多一个）+ token_plain（用户 Token 的明文）

用户 Token 让 API 调用以该用户身份进行（可用词典、查询历史、生词本都算在用户名下）。
管理后台要能随时复制它，所以用户 Token 额外保存明文；普通 Token 仍只存哈希，token_plain 为空。

只加可空列与索引，SQLite 原生 ADD COLUMN 即可，不重建表。

Revision ID: c7d9e1f3a5b2
Revises: b4e6a8c0d2f4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7d9e1f3a5b2"
down_revision: Union[str, None] = "b4e6a8c0d2f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("api_tokens")}
    if "user_id" not in existing:
        op.execute("ALTER TABLE api_tokens ADD COLUMN user_id INTEGER REFERENCES users (id)")
    if "token_plain" not in existing:
        op.add_column("api_tokens", sa.Column("token_plain", sa.String(128), nullable=True))
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_api_tokens_user_id ON api_tokens (user_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_api_tokens_user_id")
    with op.batch_alter_table("api_tokens") as batch_op:
        batch_op.drop_column("token_plain")
        batch_op.drop_column("user_id")
