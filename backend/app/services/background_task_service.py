import threading
from datetime import datetime, timezone
from typing import Any


class BackgroundTask:
    STATUS_RUNNING = "running"

    def __init__(self, task_id: int, task_type: str, title: str):
        self.id = task_id
        self.task_type = task_type
        self.title = title
        self.status = self.STATUS_RUNNING
        self.progress_data: dict[str, Any] = {}
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_type": self.task_type,
            "title": self.title,
            "status": self.status,
            "progress_data": self.progress_data,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class BackgroundTaskService:
    """进程内登记当前正在跑的长任务（目前只有词典导入），供别的会话/标签页打开
    管理后台时也能看到"正在导入"的状态。只保留运行中的任务，一结束（成功/失败）
    立即从登记表移除——不做历史记录，不持久化，随进程重启清空。"""

    def __init__(self) -> None:
        self._tasks: dict[int, BackgroundTask] = {}
        self._lock = threading.Lock()
        self._next_id = 1

    def start(self, task_type: str, title: str) -> BackgroundTask:
        with self._lock:
            task = BackgroundTask(self._next_id, task_type, title)
            self._next_id += 1
            self._tasks[task.id] = task
            return task

    def update_progress(self, task_id: int, progress_data: dict[str, Any]) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.progress_data = progress_data
            task.updated_at = datetime.now(timezone.utc)

    def finish(self, task_id: int) -> None:
        with self._lock:
            self._tasks.pop(task_id, None)

    def list_running(self) -> list[dict]:
        with self._lock:
            tasks = sorted(self._tasks.values(), key=lambda t: t.created_at)
            return [t.to_dict() for t in tasks]


background_tasks = BackgroundTaskService()
