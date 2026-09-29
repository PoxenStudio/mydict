"""users.admin_allowed_dictionary_ids：管理员划定的「可用词典」上限，与用户自选分开存

之前管理员与用户写的是同一列 allowed_dictionary_ids，用户在前台「词典选择」里改回「全部」
就把管理员的限制抹掉了。拆开后实际生效的是两列的交集。

回填：用户自选不记审计日志，管理员的每次设置都有 `user.set_allowed_dictionaries` 审计，
取每个用户最近一条作为上限；用户列与之相同时说明就是管理员设的，清成 NULL（上限内全选）。

Revision ID: d1e3f5a7b9c2
Revises: c7d9e1f3a5b2
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e3f5a7b9c2"
down_revision: Union[str, None] = "c7d9e1f3a5b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "admin_allowed_dictionary_ids" not in existing:
        op.add_column("users", sa.Column("admin_allowed_dictionary_ids", sa.JSON(), nullable=True))

    rows = bind.execute(
        sa.text(
            "SELECT target, detail FROM audit_logs "
            "WHERE action = 'user.set_allowed_dictionaries' ORDER BY id"
        )
    ).fetchall()
    latest: dict[int, list[int] | None] = {}
    for target, detail in rows:
        if not target or not target.isdigit():
            continue
        try:
            ids = json.loads(detail)["dictionary_ids"] if detail else None
        except (ValueError, KeyError, TypeError):
            continue
        latest[int(target)] = ids or None

    for user_id, limit in latest.items():
        own = bind.execute(
            sa.text("SELECT allowed_dictionary_ids FROM users WHERE id = :id"), {"id": user_id}
        ).scalar()
        if isinstance(own, str):
            own = json.loads(own)
        params = {"id": user_id, "limit": json.dumps(limit) if limit is not None else None}
        if own == limit:
            bind.execute(
                sa.text(
                    "UPDATE users SET admin_allowed_dictionary_ids = :limit, "
                    "allowed_dictionary_ids = NULL WHERE id = :id"
                ),
                params,
            )
        else:
            bind.execute(
                sa.text("UPDATE users SET admin_allowed_dictionary_ids = :limit WHERE id = :id"),
                params,
            )


def downgrade() -> None:
    # 合回一列：有上限时以上限为准，保证降级后用户不会查到上限外的词典
    op.execute(
        "UPDATE users SET allowed_dictionary_ids = admin_allowed_dictionary_ids "
        "WHERE admin_allowed_dictionary_ids IS NOT NULL"
    )
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("admin_allowed_dictionary_ids")
