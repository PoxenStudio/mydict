"""启动流程：HTTP 服务先起来，数据库迁移等耗时处理放到后台线程。

迁移在大库上可能要几十分钟，若在监听端口之前同步执行，期间页面根本打不开、看不到任何提示。
现在服务一启动就能响应 /api/system/status 与静态页面，业务接口在就绪前由 MaintenanceGate
统一返回 503。
"""

import logging
import threading
from enum import StrEnum

from app.core import migrate
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.services import dictionary_service, random_entry_service, settings_service
from app.services.background_task_service import background_tasks
from app.tasks.scheduler import start_scheduler

logger = logging.getLogger("mydict.bootstrap")


class Phase(StrEnum):
    STARTING = "starting"
    MIGRATING = "migrating"
    FAILED = "failed"
    READY = "ready"


_MIGRATING_MESSAGE = "正在升级数据库，稍候即可恢复服务。"
_MIGRATING_HEAVY_MESSAGE = (
    "正在升级数据库，其中包含整表重建，大型词库可能需要几十分钟，期间暂停服务。"
)
_FAILED_MESSAGE = "数据库升级失败，请管理员查看服务日志后重启服务，升级会从中断处继续。"

_lock = threading.Lock()
_phase = Phase.STARTING
_message: str | None = None


def _set(phase: Phase, message: str | None) -> None:
    global _phase, _message
    with _lock:
        _phase, _message = phase, message


def snapshot() -> tuple[Phase, str | None]:
    with _lock:
        return _phase, _message


def is_ready() -> bool:
    return _phase is Phase.READY


def run() -> None:
    """执行启动流程直到就绪或失败。失败时进程不退出，停在 FAILED 让页面能展示原因。"""
    try:
        pending = migrate.pending_migrations()
        if pending:
            _migrate(pending)
    except migrate.MigrationBlockedError as exc:
        logger.error("数据库升级无法开始：%s", exc)
        _set(Phase.FAILED, str(exc))
        return
    except Exception:
        logger.exception("数据库升级失败")
        _set(Phase.FAILED, _FAILED_MESSAGE)
        return
    if get_settings().enable_scheduler:
        start_scheduler()
    _warm_random_bounds()
    _sync_dictionary_resources()
    _set(Phase.READY, None)


def _sync_dictionary_resources() -> None:
    """补存量词典缺的附属资源（.mdx 同级的样式表/脚本/字体/配置）。

    上游会给附属资源的白名单增补扩展名（如 `.ini`），但那只对**新导入**的词典生效，
    已导入词典的 res/ 不会自己更新——升级完镜像问题照旧。这里每次启动补一次缺，
    代价是几十部词典各一次目录列举，跑在独立线程里，不阻塞就绪。
    """
    dictionary_service.sync_sibling_resources_in_background()


def _warm_random_bounds() -> None:
    """随机浏览开着时，启动后在后台把词典主键区间算好（不阻塞就绪）。

    首个点击【随机】的人因此不必替所有人等那次 2 秒级扫描；关着时一个查询都不发。
    """
    db = SessionLocal()
    try:
        enabled = settings_service.get_bool_setting(db, "random_browse_enabled", False)
    except Exception:
        logger.warning("读取随机浏览开关失败，跳过区间缓存预热", exc_info=True)
        return
    finally:
        db.close()
    if enabled:
        random_entry_service.warm_bounds_in_background()


def _migrate(pending: list[migrate.PendingMigration]) -> None:
    heavy = any(item.heavy for item in pending)
    _set(Phase.MIGRATING, _MIGRATING_HEAVY_MESSAGE if heavy else _MIGRATING_MESSAGE)
    task = background_tasks.start("system_migration", "升级数据库", public=True)

    def on_step(index: int, item: migrate.PendingMigration) -> None:
        background_tasks.update_progress(
            task.id, {"done": index - 1, "total": len(pending), "stage": item.title}
        )

    try:
        migrate.run_migrations(pending, on_step)
    except Exception as exc:
        background_tasks.fail(task.id, str(exc))
        raise
    background_tasks.succeed(task.id, {"total": len(pending)})


def start_in_background() -> None:
    threading.Thread(target=run, name="mydict-bootstrap", daemon=True).start()
