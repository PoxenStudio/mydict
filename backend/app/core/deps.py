from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import AUD_ADMIN, AUD_USER, decode_token
from app.models.admin import Admin
from app.models.user import User

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
