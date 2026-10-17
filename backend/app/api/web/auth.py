import jwt
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_user
from app.core.exceptions import UnauthorizedError
from app.core.security import AUD_USER, create_access_token, decode_token
from app.core.session_cookie import USER_SESSION_COOKIE, clear_session_cookie, set_session_cookie
from app.models.user import User
from app.schemas.auth import RefreshRequest, TokenPairResponse
from app.schemas.dictionary import AllowedDictionaryIdsRequest
from app.schemas.user import (
    ChangePasswordRequest,
    UserApiTokenOut,
    UserLoginRequest,
    UserPublic,
    UserRegisterRequest,
)
from app.services import token_service
from app.services.user_auth_service import (
    authenticate_user,
    change_password,
    register_user,
    set_allowed_dictionaries,
)

router = APIRouter(prefix="/auth", tags=["user-auth"])


@router.post("/register", response_model=UserPublic)
def register(body: UserRegisterRequest, db: Session = Depends(get_db)) -> User:
    return register_user(db, body.username, body.password, body.email)


@router.post("/login", response_model=TokenPairResponse)
def login(
    body: UserLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenPairResponse:
    tokens = authenticate_user(db, body.username, body.password)
    # 网页端登录态载体：refresh token 存 HttpOnly cookie（7 天，刷新时滑动续期）。
    # 响应体仍然返回 token 对，桌面端/扩展继续按 Bearer 使用，互不影响。
    set_session_cookie(response, USER_SESSION_COOKIE, tokens.refresh_token, request)
    return tokens


@router.post("/refresh", response_model=TokenPairResponse)
def refresh(body: RefreshRequest, request: Request, response: Response) -> TokenPairResponse:
    # 网页端请求体为空 → 用 cookie；桌面端/扩展显式传 refresh_token。
    # cookie 优先：请求体里的 token 只服务桌面端/扩展这类显式携带的客户端。
    # 反过来（body 优先）会让跨站请求用一个 attack token 覆盖掉浏览器现有 cookie（会话固定）。
    cookie_token = request.cookies.get(USER_SESSION_COOKIE)
    token = cookie_token or body.refresh_token
    if not token:
        raise UnauthorizedError("缺少刷新凭证")
    try:
        payload = decode_token(token, aud=AUD_USER)
    except jwt.PyJWTError as exc:
        clear_session_cookie(response, USER_SESSION_COOKIE, request)
        raise UnauthorizedError("刷新凭证无效或已过期") from exc
    if payload.get("scope") != "refresh":
        raise UnauthorizedError("凭证类型不正确")
    user_id = int(payload["sub"])
    # 滑动续期：每次刷新都把 cookie 的 7 天重新计时
    # 只续期「本来就是 cookie 会话」的请求；显式传 body token 的客户端不落 cookie，
    # 避免跨站请求凭空种下一个攻击者可控的会话 cookie。
    if cookie_token:
        set_session_cookie(response, USER_SESSION_COOKIE, token, request)
    return TokenPairResponse(
        access_token=create_access_token(user_id, AUD_USER),
        # cookie 分支不回显 refresh token：它只该待在 HttpOnly cookie 里
        refresh_token=None if cookie_token else token,
    )


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    clear_session_cookie(response, USER_SESSION_COOKIE, request)
    return {"ok": True}


@router.post("/change-password")
def change_password_route(
    body: ChangePasswordRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    change_password(db, user, body.old_password, body.new_password)
    return {"ok": True}


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(require_user)) -> User:
    return user


@router.put("/allowed-dictionaries", response_model=UserPublic)
def set_allowed_dictionaries_route(
    body: AllowedDictionaryIdsRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> User:
    return set_allowed_dictionaries(db, user, body.dictionary_ids)


@router.get("/api-token", response_model=UserApiTokenOut)
def get_api_token(
    user: User = Depends(require_user), db: Session = Depends(get_db)
) -> UserApiTokenOut:
    """当前用户自己的 API Token（以本人身份调用对外 API），没有时 api_token 为空。"""
    token = token_service.find_user_token(db, user.id)
    return UserApiTokenOut(api_token=token.token_plain if token else None)


@router.post("/api-token", response_model=UserApiTokenOut)
def issue_api_token(
    user: User = Depends(require_user), db: Session = Depends(get_db)
) -> UserApiTokenOut:
    """自助分配 API Token；已有则重新分配，旧值立即失效。"""
    token = token_service.issue_user_token(db, user, admin_id=None)
    return UserApiTokenOut(api_token=token.token_plain)
