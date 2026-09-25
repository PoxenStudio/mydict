import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.core.config import get_settings

logger = logging.getLogger("mydict.migrate")


@dataclass(frozen=True, slots=True)
class PendingMigration:
    revision: str
    title: str
    # 迁移脚本里声明 `heavy = True` 的：会整表重建 dict_entries 之类的大表，大库上要跑
    # 很久、需要与表同等大小的额外磁盘
    heavy: bool


class MigrationBlockedError(Exception):
    """迁移无法开始（如磁盘空间不足）。消息不含路径等内部信息，可直接展示给访客。"""


def _alembic_config(*, keep_app_logging: bool = False) -> Config:
    backend_root = Path(__file__).resolve().parent.parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    # 应用内迁移时不让 env.py 按 alembic.ini 重配 root logger，否则应用日志会被冲掉
    cfg.attributes["keep_app_logging"] = keep_app_logging
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


def check_disk_space(pending: list[PendingMigration]) -> None:
    if not any(item.heavy for item in pending):
        return
    db_size, free = free_space_for_database()
    if free < db_size:
        raise MigrationBlockedError(
            f"数据库升级需要约与数据库同等大小的剩余磁盘空间（数据库 {db_size / 1024**3:.1f}GB，"
            f"剩余 {free / 1024**3:.1f}GB），请管理员腾出空间后重启服务。"
        )


def run_migrations(
    pending: list[PendingMigration] | None = None,
    on_step: Callable[[int, PendingMigration], None] | None = None,
) -> None:
    """逐个执行待执行的迁移，每开始一个回调一次 on_step(序号, 迁移)，供启动流程报告进度。

    重型迁移同样自动执行（多数部署者没有条件停机手动跑），先检查磁盘空间。重型迁移必须能从
    任意中断点重跑：执行期间容器被重启/杀掉，下次启动会接着收拾。
    """
    if pending is None:
        pending = pending_migrations()
    if not pending:
        return
    check_disk_space(pending)
    heavy = [item for item in pending if item.heavy]
    if heavy:
        names = "、".join(f"{item.revision}（{item.title}）" for item in heavy)
        logger.warning("正在执行重型迁移：%s。大库上可能要几十分钟，期间服务暂停。", names)
    for index, item in enumerate(pending, start=1):
        if on_step is not None:
            on_step(index, item)
        command.upgrade(_alembic_config(keep_app_logging=True), item.revision)
