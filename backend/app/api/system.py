from fastapi import APIRouter

from app.core.version import get_app_version
from app.schemas.system import SystemInfoOut

router = APIRouter()


@router.get("/system/info", response_model=SystemInfoOut)
def system_info() -> SystemInfoOut:
    return SystemInfoOut(version=get_app_version())
