from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import AUD_ADMIN, AUD_USER, decode_token, hash_api_token
from app.models.admin import Admin
from app.models.token import ApiToken
from app.models.user import User
from app.services.settings_service import get_bool_setting

bearer_scheme = HTTPBearer(auto_error=False)
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def require_admin(credentials: Credentials, db: Session = Depends(get_db)) -> Admin:
    if credentials is None:
        raise UnauthorizedError("缺少管理员登录凭证")
    try:
        payload = decode_token(credentials.credentials, aud=AUD_ADMIN)
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("登录凭证无效或已过期") from exc
    if payload.get("scope") != "access":
        raise UnauthorizedError("登录凭证类型不正确")
    admin = db.get(Admin, int(payload["sub"]))
    if admin is None:
        raise UnauthorizedError("管理员不存在")
    return admin


def require_user(credentials: Credentials, db: Session = Depends(get_db)) -> User:
    if credentials is None:
        raise UnauthorizedError("缺少登录凭证")
    try:
        payload = decode_token(credentials.credentials, aud=AUD_USER)
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("登录凭证无效或已过期") from exc
    if payload.get("scope") != "access":
        raise UnauthorizedError("登录凭证类型不正确")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise UnauthorizedError("用户不存在")
    if user.status != "active":
        raise ForbiddenError("账号已被禁用")
    return user


def _resolve_api_token(credentials: HTTPAuthorizationCredentials, db: Session) -> ApiToken:
    token_hash = hash_api_token(credentials.credentials)
    token = db.query(ApiToken).filter(ApiToken.token_hash == token_hash).first()
    if token is None:
        raise UnauthorizedError("Token 无效")
    if token.status != "active":
        raise ForbiddenError("Token 已被禁用")
    token.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return token


def require_api_token(credentials: Credentials, db: Session = Depends(get_db)) -> ApiToken:
    """收藏类接口专用：始终要求携带有效 Token，不受「开放使用」设置影响。"""
    if credentials is None:
        raise UnauthorizedError("缺少 Token")
    return _resolve_api_token(credentials, db)


@dataclass
class ApiCaller:
    """查询类接口的调用方：token 非空表示已鉴权的第三方；为空表示「开放使用」放行的匿名调用。"""

    token: ApiToken | None
    ip: str | None


def get_api_caller(
    request: Request,
    credentials: Credentials,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ApiCaller:
    if credentials is not None:
        return ApiCaller(token=_resolve_api_token(credentials, db), ip=None)
    if not get_bool_setting(db, "open_access", settings.open_access_default):
        raise UnauthorizedError("需要提供有效的 Token，或由管理员开启「开放使用」")
    ip = request.client.host if request.client else "unknown"
    return ApiCaller(token=None, ip=ip)


@dataclass
class WebCaller:
    """Web 端查询接口的调用方：user 非空表示已登录用户；为空表示「开放使用」放行的访客。"""

    user: User | None
    ip: str | None


def get_web_caller(
    request: Request,
    credentials: Credentials,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WebCaller:
    if credentials is not None:
        try:
            payload = decode_token(credentials.credentials, aud=AUD_USER)
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("登录凭证无效或已过期") from exc
        if payload.get("scope") != "access":
            raise UnauthorizedError("登录凭证类型不正确")
        user = db.get(User, int(payload["sub"]))
        if user is None:
            raise UnauthorizedError("用户不存在")
        if user.status != "active":
            raise ForbiddenError("账号已被禁用")
        return WebCaller(user=user, ip=None)
    if not get_bool_setting(db, "open_access", settings.open_access_default):
        raise UnauthorizedError("需要登录，或由管理员开启「开放使用」")
    ip = request.client.host if request.client else "unknown"
    return WebCaller(user=None, ip=ip)
