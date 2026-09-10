import jwt
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.core.exceptions import UnauthorizedError
from app.core.security import AUD_ADMIN, create_access_token, decode_token
from app.models.admin import Admin
from app.schemas.admin import AdminLoginRequest, AdminSetupRequest, BootstrapStatusResponse
from app.schemas.auth import RefreshRequest, TokenPairResponse
from app.services.admin_auth_service import authenticate_admin, is_initialized, setup_admin

router = APIRouter(prefix="/admin", tags=["admin-auth"])


@router.get("/bootstrap-status", response_model=BootstrapStatusResponse)
def bootstrap_status(db: Session = Depends(get_db)) -> BootstrapStatusResponse:
    return BootstrapStatusResponse(initialized=is_initialized(db))


@router.post("/setup", response_model=TokenPairResponse)
def setup(body: AdminSetupRequest, db: Session = Depends(get_db)) -> TokenPairResponse:
    setup_admin(db, body.username, body.password)
    return authenticate_admin(db, body.username, body.password)


@router.post("/login", response_model=TokenPairResponse)
def login(body: AdminLoginRequest, db: Session = Depends(get_db)) -> TokenPairResponse:
    return authenticate_admin(db, body.username, body.password)


@router.post("/refresh", response_model=TokenPairResponse)
def refresh(body: RefreshRequest) -> TokenPairResponse:
    try:
        payload = decode_token(body.refresh_token, aud=AUD_ADMIN)
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("刷新凭证无效或已过期") from exc
    if payload.get("scope") != "refresh":
        raise UnauthorizedError("凭证类型不正确")
    admin_id = int(payload["sub"])
    return TokenPairResponse(
        access_token=create_access_token(admin_id, AUD_ADMIN),
        refresh_token=body.refresh_token,
    )


@router.get("/me")
def me(admin: Admin = Depends(require_admin)) -> dict[str, int | str]:
    return {"id": admin.id, "username": admin.username}
