from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# 确保所有 model 模块被 import，Base.metadata 才能收集到全部表结构
from app import models  # noqa: F401
from app.core.config import get_settings
from app.core.db import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None and not config.attributes.get("keep_app_logging"):
    # disable_existing_loggers 默认 True 会把应用自己已创建的 logger（如 mydict.auth）
    # 标记为 disabled，导致迁移跑完之后这些 logger 永久失效，改成 False 避免误伤
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
