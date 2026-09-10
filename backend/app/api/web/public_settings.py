from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.schemas.settings import PublicSettingsOut
from app.services import admin_settings_service

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/settings", response_model=PublicSettingsOut)
def public_settings(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> PublicSettingsOut:
    return admin_settings_service.get_public_settings(db, settings)
