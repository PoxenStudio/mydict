import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.core.config import get_settings

# 词条表超过这个行数时，重型迁移（见 PendingMigration.heavy）不在启动时自动跑
HEAVY_MIGRATION_ROW_THRESHOLD = 100_000


@dataclass(frozen=True, slots=True)
class PendingMigration:
    revision: str
    title: str
    # 迁移脚本里声明 `heavy = True` 的：会整表重建 dict_entries 之类的大表，生产库上要跑
    # 很久、需要与表同等大小的额外磁盘，必须停机手动执行
    heavy: bool


def _alembic_config() -> Config:
    backend_root = Path(__file__).resolve().parent.parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    return cfg


def _current_revision() -> str | None:
    engine = create_engine(get_settings().database_url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def pending_migrations() -> list[PendingMigration]:
    """按执行顺序返回尚未应用的迁移。"""
    script = ScriptDirectory.from_config(_alembic_config())
    revisions = list(script.iterate_revisions("heads", _current_revision()))
    revisions.reverse()
    return [
        PendingMigration(
            revision=rev.revision,
            title=(rev.doc or "").strip().splitlines()[0] if rev.doc else "",
            heavy=bool(getattr(rev.module, "heavy", False)),
        )
        for rev in revisions
    ]


def dict_entries_row_count(limit: int) -> int:
    """dict_entries 的行数，数到 limit 为止（只用来判断「大不大」，不必数完 2000 多万行）。"""
    engine = create_engine(get_settings().database_url)
    try:
        with engine.connect() as connection:
            if "dict_entries" not in inspect(connection).get_table_names():
                return 0
            return connection.execute(
                text("SELECT COUNT(*) FROM (SELECT 1 FROM dict_entries LIMIT :n)"),
                {"n": limit},
            ).scalar_one()
    finally:
        engine.dispose()


def free_space_for_database() -> tuple[int, int]:
    """返回 (数据库文件大小, 所在磁盘剩余空间)，单位字节。"""
    database = Path(get_settings().database_path)
    size = database.stat().st_size if database.exists() else 0
    return size, shutil.disk_usage(database.parent).free


def upgrade_to_head() -> None:
    command.upgrade(_alembic_config(), "head")


def run_migrations() -> None:
    """启动时的自动迁移。

    轻量迁移照常自动跑；有**重型**迁移待执行、且词条表已经有相当数据量时拒绝启动，要求
    停机后用 `python -m app.cli migrate --yes` 手动执行。原因是自动跑会把服务卡在启动阶段
    几十分钟，期间容器一旦被重启/杀掉，SQLite 的非事务 DDL 会留下半截状态。

    AUTO_MIGRATE=false 时完全不自动迁移：有待执行的迁移就拒绝启动。
    """
    pending = pending_migrations()
    if not pending:
        return
    if not get_settings().auto_migrate:
        raise SystemExit(
            f"数据库有 {len(pending)} 个待执行的迁移，而 AUTO_MIGRATE=false。"
            "请停止服务后执行 `python -m app.cli migrate --yes`，再启动。"
        )
    heavy = [item for item in pending if item.heavy]
    if heavy and dict_entries_row_count(HEAVY_MIGRATION_ROW_THRESHOLD + 1) > (
        HEAVY_MIGRATION_ROW_THRESHOLD
    ):
        names = "、".join(f"{item.revision}（{item.title}）" for item in heavy)
        raise SystemExit(
            f"有重型迁移待执行：{names}。它会整表重建词条表，在大库上要跑很久、并需要与数据库"
            "同等大小的剩余磁盘空间，不能在启动时自动执行。请停止服务，先执行 "
            "`python -m app.cli migrate` 查看计划，确认后加 `--yes` 执行，完成后再启动。"
        )
    upgrade_to_head()
