import jwt
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.core.exceptions import UnauthorizedError
from app.core.security import AUD_ADMIN, create_access_token, decode_token
from app.core.session_cookie import ADMIN_SESSION_COOKIE, clear_session_cookie, set_session_cookie
from app.models.admin import Admin
from app.schemas.admin import AdminLoginRequest, AdminSetupRequest, BootstrapStatusResponse
from app.schemas.auth import RefreshRequest, TokenPairResponse
from app.services.admin_auth_service import authenticate_admin, is_initialized, setup_admin

router = APIRouter(prefix="/admin", tags=["admin-auth"])


@router.get("/bootstrap-status", response_model=BootstrapStatusResponse)
def bootstrap_status(db: Session = Depends(get_db)) -> BootstrapStatusResponse:
    return BootstrapStatusResponse(initialized=is_initialized(db))


@router.post("/setup", response_model=TokenPairResponse)
def setup(
    body: AdminSetupRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> TokenPairResponse:
    setup_admin(db, body.username, body.password)
    tokens = authenticate_admin(db, body.username, body.password)
    set_session_cookie(response, ADMIN_SESSION_COOKIE, tokens.refresh_token, request)
    return tokens


@router.post("/login", response_model=TokenPairResponse)
def login(
    body: AdminLoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> TokenPairResponse:
    tokens = authenticate_admin(db, body.username, body.password)
    # 与用户端一致：refresh token 放 HttpOnly cookie，7 天滑动续期
    set_session_cookie(response, ADMIN_SESSION_COOKIE, tokens.refresh_token, request)
    return tokens


@router.post("/refresh", response_model=TokenPairResponse)
def refresh(body: RefreshRequest, request: Request, response: Response) -> TokenPairResponse:
    token = body.refresh_token or request.cookies.get(ADMIN_SESSION_COOKIE)
    if not token:
        raise UnauthorizedError("缺少刷新凭证")
    try:
        payload = decode_token(token, aud=AUD_ADMIN)
    except jwt.PyJWTError as exc:
        clear_session_cookie(response, ADMIN_SESSION_COOKIE, request)
        raise UnauthorizedError("刷新凭证无效或已过期") from exc
    if payload.get("scope") != "refresh":
        raise UnauthorizedError("凭证类型不正确")
    admin_id = int(payload["sub"])
    set_session_cookie(response, ADMIN_SESSION_COOKIE, token, request)
    return TokenPairResponse(
        access_token=create_access_token(admin_id, AUD_ADMIN),
        refresh_token=token,
    )


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    clear_session_cookie(response, ADMIN_SESSION_COOKIE, request)
    return {"ok": True}


@router.get("/me")
def me(admin: Admin = Depends(require_admin)) -> dict[str, int | str]:
    return {"id": admin.id, "username": admin.username}
