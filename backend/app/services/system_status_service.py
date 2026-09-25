from datetime import datetime, timezone

from app.core import bootstrap
from app.services.background_task_service import background_tasks

_BUSY_NOTICE = "后台正在处理词典数据，查询可能稍慢。"


def get_status() -> dict:
    """给未登录访客看的系统状态：只读内存，不碰数据库（迁移期间数据库被独占）。

    公开任务（启动时的迁移）给出标题与进度；管理员发起的词典处理只给一句概括，不暴露词典名。
    """
    phase, message = bootstrap.snapshot()
    now = datetime.now(timezone.utc)
    running = background_tasks.list_running()
    tasks = [
        {
            "id": task["id"],
            "title": task["title"],
            "stage": task["progress_data"].get("stage"),
            "done": task["progress_data"].get("done"),
            "total": task["progress_data"].get("total"),
            "elapsed_seconds": int((now - task["created_at"]).total_seconds()),
        }
        for task in running
        if task["public"]
    ]
    busy = phase is bootstrap.Phase.READY and any(not task["public"] for task in running)
    return {
        "phase": phase.value,
        "blocking": phase is not bootstrap.Phase.READY,
        "message": message,
        "tasks": tasks,
        "busy_notice": _BUSY_NOTICE if busy else None,
    }
