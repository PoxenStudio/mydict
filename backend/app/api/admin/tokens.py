from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.models.admin import Admin
from app.schemas.token import TokenCreateRequest, TokenCreateResponse, TokenOut
from app.services import token_service

router = APIRouter(prefix="/admin/tokens", tags=["admin-tokens"])


@router.get("", response_model=list[TokenOut])
def list_tokens(
    db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)
) -> list[TokenOut]:
    return token_service.list_tokens(db)


@router.post("", response_model=TokenCreateResponse)
def create_token(
    body: TokenCreateRequest,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_admin),
) -> TokenCreateResponse:
    return token_service.create_token(db, body.name, body.daily_limit, admin.id)


@router.put("/{token_id}/enable", response_model=TokenOut)
def enable(
    token_id: int, db: Session = Depends(get_db), admin: Admin = Depends(require_admin)
) -> TokenOut:
    return token_service.set_token_status(db, token_id, "active", admin.id)


@router.put("/{token_id}/disable", response_model=TokenOut)
def disable(
    token_id: int, db: Session = Depends(get_db), admin: Admin = Depends(require_admin)
) -> TokenOut:
    return token_service.set_token_status(db, token_id, "disabled", admin.id)


@router.post("/{token_id}/regenerate", response_model=TokenCreateResponse)
def regenerate(
    token_id: int, db: Session = Depends(get_db), admin: Admin = Depends(require_admin)
) -> TokenCreateResponse:
    return token_service.regenerate_token(db, token_id, admin.id)


@router.get("/{token_id}/vocab-count")
def vocab_count(
    token_id: int, db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)
) -> dict[str, int]:
    return {"count": token_service.get_vocab_count(db, token_id)}
