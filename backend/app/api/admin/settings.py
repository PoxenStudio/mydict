from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.deps import require_admin
from app.models.admin import Admin
from app.schemas.settings import (
    SpxTranscodeStatusOut,
    SystemSettingsOut,
    SystemSettingsUpdateRequest,
)
from app.services import admin_settings_service, spx_transcode

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])


@router.get("", response_model=SystemSettingsOut)
def get_settings_endpoint(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _admin: Admin = Depends(require_admin),
) -> SystemSettingsOut:
    return admin_settings_service.get_all_settings(db, settings)


@router.put("", response_model=SystemSettingsOut)
def update_settings_endpoint(
    body: SystemSettingsUpdateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    admin: Admin = Depends(require_admin),
) -> SystemSettingsOut:
    return admin_settings_service.update_settings(
        db, body.model_dump(), body.model_fields_set, settings, admin.id
    )


@router.get("/spx-transcode", response_model=SpxTranscodeStatusOut)
def spx_transcode_status(
    refresh: bool = False,
    _admin: Admin = Depends(require_admin),
) -> SpxTranscodeStatusOut:
    """发音转码的运行状态。

    available 为 false 表示容器里找不到 ffmpeg —— 它不随镜像分发（GPL/LGPL 与项目 MIT
    授权不兼容），需要自行挂载；此时开关怎么设都不会转码。

    refresh=true 时忽略进程内缓存重新探测：探测结果默认只算一次（容器里的 ffmpeg 不会
    中途出现），而后台「重新检测」按钮恰恰用于「我刚挂上，别看旧结果」。
    """
    return spx_transcode.status(refresh=refresh)
