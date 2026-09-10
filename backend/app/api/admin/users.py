from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.models.admin import Admin
from app.schemas.admin_user import (
    AdminUserCreateRequest,
    AdminUserCreateResponse,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AdminUserOut,
    ResetPasswordResponse,
)
from app.services import user_admin_service

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.post("", response_model=AdminUserCreateResponse)
def create(
    body: AdminUserCreateRequest,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_admin),
) -> AdminUserCreateResponse:
    user, temp_password = user_admin_service.create_user(db, body.username, body.email, admin.id)
    return AdminUserCreateResponse(user=user, temporary_password=temp_password)


@router.get("", response_model=AdminUserListResponse)
def list_users(
    search: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> AdminUserListResponse:
    items, total = user_admin_service.list_users(db, search, status, page, min(page_size, 100))
    return AdminUserListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{user_id}", response_model=AdminUserDetailResponse)
def user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> AdminUserDetailResponse:
    return user_admin_service.get_user_detail(db, user_id)


@router.put("/{user_id}/enable", response_model=AdminUserOut)
def enable(
    user_id: int, db: Session = Depends(get_db), admin: Admin = Depends(require_admin)
) -> AdminUserOut:
    return user_admin_service.set_user_status(db, user_id, "active", admin.id)


@router.put("/{user_id}/disable", response_model=AdminUserOut)
def disable(
    user_id: int, db: Session = Depends(get_db), admin: Admin = Depends(require_admin)
) -> AdminUserOut:
    return user_admin_service.set_user_status(db, user_id, "disabled", admin.id)


@router.post("/{user_id}/reset-password", response_model=ResetPasswordResponse)
def reset_password(
    user_id: int, db: Session = Depends(get_db), admin: Admin = Depends(require_admin)
) -> ResetPasswordResponse:
    temp = user_admin_service.reset_user_password(db, user_id, admin.id)
    return ResetPasswordResponse(temporary_password=temp)
