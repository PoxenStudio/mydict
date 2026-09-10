import jwt
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_user
from app.core.exceptions import UnauthorizedError
from app.core.security import AUD_USER, create_access_token, decode_token
from app.models.user import User
from app.schemas.auth import RefreshRequest, TokenPairResponse
from app.schemas.user import (
    ChangePasswordRequest,
    UserLoginRequest,
    UserPublic,
    UserRegisterRequest,
)
from app.services.user_auth_service import authenticate_user, change_password, register_user

router = APIRouter(prefix="/auth", tags=["user-auth"])


@router.post("/register", response_model=UserPublic)
def register(body: UserRegisterRequest, db: Session = Depends(get_db)) -> User:
    return register_user(db, body.username, body.password, body.email)


@router.post("/login", response_model=TokenPairResponse)
def login(body: UserLoginRequest, db: Session = Depends(get_db)) -> TokenPairResponse:
    return authenticate_user(db, body.username, body.password)


@router.post("/refresh", response_model=TokenPairResponse)
def refresh(body: RefreshRequest) -> TokenPairResponse:
    try:
        payload = decode_token(body.refresh_token, aud=AUD_USER)
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("刷新凭证无效或已过期") from exc
    if payload.get("scope") != "refresh":
        raise UnauthorizedError("凭证类型不正确")
    user_id = int(payload["sub"])
    return TokenPairResponse(
        access_token=create_access_token(user_id, AUD_USER),
        refresh_token=body.refresh_token,
    )


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
