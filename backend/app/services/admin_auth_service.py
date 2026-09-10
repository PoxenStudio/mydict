from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import AdminAlreadyInitializedError, InvalidCredentialsError
from app.core.security import (
    AUD_ADMIN,
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.admin import Admin
from app.schemas.auth import TokenPairResponse
from app.services.audit_service import log_action


def is_initialized(db: Session) -> bool:
    return db.query(Admin).first() is not None


def setup_admin(db: Session, username: str, password: str) -> Admin:
    if is_initialized(db):
        raise AdminAlreadyInitializedError("管理员已初始化")
    admin = Admin(username=username, password_hash=hash_password(password))
    db.add(admin)
    db.commit()
    db.refresh(admin)
    log_action(db, actor_type="admin", actor_id=admin.id, action="admin.setup", target=username)
    return admin


def authenticate_admin(db: Session, username: str, password: str) -> TokenPairResponse:
    admin = db.query(Admin).filter(Admin.username == username).first()
    if admin is None or not verify_password(password, admin.password_hash):
        raise InvalidCredentialsError("用户名或密码错误")
    admin.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return TokenPairResponse(
        access_token=create_access_token(admin.id, AUD_ADMIN),
        refresh_token=create_refresh_token(admin.id, AUD_ADMIN),
    )
