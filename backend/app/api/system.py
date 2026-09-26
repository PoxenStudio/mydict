from fastapi import APIRouter

from app.core.version import get_app_version
from app.schemas.system import SystemInfoOut, SystemStatusOut
from app.services import system_status_service

router = APIRouter()


@router.get("/system/info", response_model=SystemInfoOut)
def system_info() -> SystemInfoOut:
    return SystemInfoOut(version=get_app_version())


@router.get("/system/status", response_model=SystemStatusOut)
def system_status() -> dict:
    return system_status_service.get_status()
