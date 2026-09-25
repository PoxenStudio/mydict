import threading
from datetime import datetime, timezone
from typing import Any

# 已结束（成功/失败）的任务保留多久供轮询方读取最终结果，超过这个时长还没人来
# 取，视为轮询方已经放弃（比如页面被关掉），清掉避免登记表无限增长。
_FINISHED_TTL_SECONDS = 600


class BackgroundTask:
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"

    def __init__(self, task_id: int, task_type: str, title: str, public: bool):
        self.id = task_id
        self.task_type = task_type
        self.title = title
        # 公开任务的标题与进度会经 /api/system/status 给未登录的访客看
        self.public = public
        self.status = self.STATUS_RUNNING
        self.progress_data: dict[str, Any] = {}
        self.result: dict[str, Any] | None = None
        self.error: str | None = None
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_type": self.task_type,
            "title": self.title,
            "public": self.public,
            "status": self.status,
            "progress_data": self.progress_data,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class BackgroundTaskService:
    """进程内登记当前正在跑的长任务（启动时的数据库迁移、词典导入/重新解析/修复）。运行中的任务供别的会话/
    标签页打开管理后台时也能看到"正在导入"的状态；发起方自己则通过 get() 轮询
    task_id 直到 status 变成 success/error，取得导入是否真正完成。不持久化，
    随进程重启清空。"""

    def __init__(self) -> None:
        self._tasks: dict[int, BackgroundTask] = {}
        self._lock = threading.Lock()
        self._next_id = 1

    def start(self, task_type: str, title: str, *, public: bool = False) -> BackgroundTask:
        with self._lock:
            self._prune_finished_locked()
            task = BackgroundTask(self._next_id, task_type, title, public)
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

    def succeed(self, task_id: int, result: dict[str, Any]) -> None:
        self._finish(task_id, BackgroundTask.STATUS_SUCCESS, result=result)

    def fail(self, task_id: int, error: str) -> None:
        self._finish(task_id, BackgroundTask.STATUS_ERROR, error=error)

    def _finish(
        self,
        task_id: int,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.status = status
            task.result = result
            task.error = error
            task.updated_at = datetime.now(timezone.utc)

    def get(self, task_id: int) -> dict | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return task.to_dict() if task else None

    def list_running(self) -> list[dict]:
        with self._lock:
            tasks = sorted(
                (t for t in self._tasks.values() if t.status == BackgroundTask.STATUS_RUNNING),
                key=lambda t: t.created_at,
            )
            return [t.to_dict() for t in tasks]

    def _prune_finished_locked(self) -> None:
        now = datetime.now(timezone.utc)
        stale_ids = [
            task_id
            for task_id, task in self._tasks.items()
            if task.status != BackgroundTask.STATUS_RUNNING
            and (now - task.updated_at).total_seconds() > _FINISHED_TTL_SECONDS
        ]
        for task_id in stale_ids:
            self._tasks.pop(task_id, None)


background_tasks = BackgroundTaskService()
