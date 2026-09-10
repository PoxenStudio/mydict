from pathlib import Path

from alembic import command
from alembic.config import Config


def run_migrations() -> None:
    """容器启动时自动对 SQLite 文件建表/升级到最新版本，见《技术方案设计.md》8.4。"""
    backend_root = Path(__file__).resolve().parent.parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    command.upgrade(cfg, "head")
