"""seed system settings

Revision ID: df2e34e6bb5e
Revises: aab5910cca85
Create Date: 2026-09-10 14:09:50.374539

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'df2e34e6bb5e'
down_revision: Union[str, None] = 'aab5910cca85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 见《技术方案设计.md》第 3 节 system_settings 预置 key 说明
DEFAULTS = {
    "open_access": "false",
    "allow_registration": "true",
    "token_default_daily_limit": "1000",
    "anonymous_ip_rate_limit_per_min": "60",
    "vocab_max_items_per_owner": "",
    "site_name": "MyDict",
}

settings_table = sa.table(
    "system_settings",
    sa.column("key", sa.String),
    sa.column("value", sa.String),
)


def upgrade() -> None:
    op.bulk_insert(settings_table, [{"key": k, "value": v} for k, v in DEFAULTS.items()])


def downgrade() -> None:
    for key in DEFAULTS:
        op.execute(settings_table.delete().where(settings_table.c.key == key))
