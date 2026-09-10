from fastapi import APIRouter, Depends

from app.core.deps import require_admin
from app.models.admin import Admin
from app.schemas.background_task import BackgroundTaskOut
from app.services.background_task_service import background_tasks

router = APIRouter(prefix="/admin/tasks", tags=["admin-tasks"])


@router.get("/running", response_model=list[BackgroundTaskOut])
def running_tasks(_admin: Admin = Depends(require_admin)) -> list[dict]:
    return background_tasks.list_running()
