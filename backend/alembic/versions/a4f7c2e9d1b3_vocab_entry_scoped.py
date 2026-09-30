"""生词本改为「词条级」：同一部词典同一个词一条，不同词典互不冲突

原来两张表的唯一键是 `(user_id, word)` / `(token_id, word)`——一个词只能存一条，
于是「中文词典的『人気』」和「NHK 的『人気』」互相顶掉，用户第二次收藏只会得到
409，而且不知道自己存的是哪一部。改成 `(owner, dictionary_id, word)`：点哪部词典的
收藏就存哪部，生词本里也带上词典名。

- 新增 `dictionary_name` 快照：词典被删后（dictionary_id 置 NULL）列表仍能显示来源。
- SQLite 不支持改约束，唯一键用 batch_alter_table 重建表实现。
- `dictionary_id` 可为 NULL（历史数据、手工 API 调用、词典被删后）：唯一索引用
  `WHERE dictionary_id IS NOT NULL` 的部分索引，NULL 那侧的重复由服务层兜住。

Revision ID: a4f7c2e9d1b3
Revises: d1e3f5a7b9c2
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4f7c2e9d1b3"
down_revision: Union[str, None] = "d1e3f5a7b9c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (表, 旧唯一键名, 新唯一索引名, 归属列)
_TABLES = (
    ("vocab_items", "uq_vocab_items_user_word", "uq_vocab_items_user_dict_word", "user_id"),
    (
        "token_vocab_items",
        "uq_token_vocab_items_token_word",
        "uq_token_vocab_items_token_dict_word",
        "token_id",
    ),
)


def upgrade() -> None:
    for table, old_name, new_name, owner in _TABLES:
        existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
        if "dictionary_name" not in existing:
            op.add_column(table, sa.Column("dictionary_name", sa.String(255), nullable=True))
        # 回填：还能找到词典的，把名字快照下来
        op.execute(
            f"UPDATE {table} SET dictionary_name = ("
            f"SELECT name FROM dictionaries d WHERE d.id = {table}.dictionary_id"
            f") WHERE dictionary_id IS NOT NULL AND dictionary_name IS NULL"
        )
        # 唯一键重建成 (owner, dictionary_id, word)
        with op.batch_alter_table(table, recreate="always") as batch:
            batch.drop_constraint(old_name, type_="unique")
        op.create_index(
            new_name,
            table,
            [owner, "dictionary_id", "word"],
            unique=True,
            sqlite_where=sa.text("dictionary_id IS NOT NULL"),
        )


def downgrade() -> None:
    for table, old_name, new_name, owner in _TABLES:
        op.drop_index(new_name, table_name=table)
        with op.batch_alter_table(table, recreate="always") as batch:
            batch.drop_column("dictionary_name")
            batch.create_unique_constraint(old_name, [owner, "word"])
