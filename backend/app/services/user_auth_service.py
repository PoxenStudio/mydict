from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    InvalidCredentialsError,
    RegistrationDisabledError,
)
from app.core.security import (
    AUD_USER,
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import TokenPairResponse
from app.services.settings_service import get_bool_setting


def register_user(db: Session, username: str, password: str, email: str | None) -> User:
    if not get_bool_setting(db, "allow_registration", default=True):
        raise RegistrationDisabledError("当前不允许注册")
    if db.query(User).filter(User.username == username).first() is not None:
        raise ConflictError("用户名已存在")
    user = User(username=username, password_hash=hash_password(password), email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> TokenPairResponse:
    user = db.query(User).filter(User.username == username).first()
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("用户名或密码错误")
    if user.status != "active":
        raise ForbiddenError("账号已被禁用")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return TokenPairResponse(
        access_token=create_access_token(user.id, AUD_USER),
        refresh_token=create_refresh_token(user.id, AUD_USER),
    )


def change_password(db: Session, user: User, old_password: str, new_password: str) -> None:
    if not verify_password(old_password, user.password_hash):
        raise InvalidCredentialsError("原密码不正确")
    user.password_hash = hash_password(new_password)
    db.commit()
