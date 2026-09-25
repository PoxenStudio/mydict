import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.core.config import get_settings


@dataclass(frozen=True, slots=True)
class PendingMigration:
    revision: str
    title: str
    # 迁移脚本里声明 `heavy = True` 的：会整表重建 dict_entries 之类的大表，大库上要跑
    # 很久、需要与表同等大小的额外磁盘
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


def free_space_for_database() -> tuple[int, int]:
    """返回 (数据库文件大小, 所在磁盘剩余空间)，单位字节。"""
    database = Path(get_settings().database_path)
    size = database.stat().st_size if database.exists() else 0
    return size, shutil.disk_usage(database.parent).free


def upgrade_to_head() -> None:
    command.upgrade(_alembic_config(), "head")


def run_migrations() -> None:
    """启动时的自动迁移。

    重型迁移同样自动执行（多数用户没有条件停机手动跑），但先检查磁盘空间、并提示可能耗时
    很久。重型迁移必须能从任意中断点重跑：启动期间容器被重启/杀掉，下次启动会接着收拾。

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
    if heavy:
        db_size, free = free_space_for_database()
        if free < db_size:
            raise SystemExit(
                f"有重型迁移待执行，需要约与数据库同等大小的剩余磁盘空间（数据库 "
                f"{db_size / 1024**3:.1f}GB，剩余 {free / 1024**3:.1f}GB）。请先腾出空间再启动。"
            )
        names = "、".join(f"{item.revision}（{item.title}）" for item in heavy)
        print(
            f"正在执行重型迁移：{names}。它会整表重建词条表，大库上可能要几十分钟，期间服务"
            "不可用，请勿停止容器；万一被中断，重启后会自动接着执行。",
            file=sys.stderr,
            flush=True,
        )
    upgrade_to_head()
