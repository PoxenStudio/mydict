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
    # cookie 优先：请求体里的 token 只服务桌面端/扩展这类显式携带的客户端。
    # 反过来（body 优先）会让跨站请求用一个 attack token 覆盖掉浏览器现有 cookie（会话固定）。
    cookie_token = request.cookies.get(ADMIN_SESSION_COOKIE)
    token = cookie_token or body.refresh_token
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
    # 只续期「本来就是 cookie 会话」的请求；显式传 body token 的客户端不落 cookie，
    # 避免跨站请求凭空种下一个攻击者可控的会话 cookie。
    if cookie_token:
        set_session_cookie(response, ADMIN_SESSION_COOKIE, token, request)
    return TokenPairResponse(
        access_token=create_access_token(admin_id, AUD_ADMIN),
        # cookie 分支不回显 refresh token：它只该待在 HttpOnly cookie 里
        refresh_token=None if cookie_token else token,
    )


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    clear_session_cookie(response, ADMIN_SESSION_COOKIE, request)
    return {"ok": True}


@router.get("/me")
def me(admin: Admin = Depends(require_admin)) -> dict[str, int | str]:
    return {"id": admin.id, "username": admin.username}
