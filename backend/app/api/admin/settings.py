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
from app.services import admin_settings_service

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


