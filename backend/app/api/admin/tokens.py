from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.models.admin import Admin
from app.schemas.dictionary import AllowedDictionaryIdsRequest
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
    return token_service.create_token(
        db, body.name, body.daily_limit, admin.id, body.allowed_dictionary_ids
    )


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


@router.put("/{token_id}/allowed-dictionaries", response_model=TokenOut)
def set_allowed_dictionaries(
    token_id: int,
    body: AllowedDictionaryIdsRequest,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_admin),
) -> TokenOut:
    return token_service.set_allowed_dictionaries(db, token_id, body.dictionary_ids, admin.id)


@router.delete("/{token_id}", status_code=204)
def delete_token(
    token_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_admin),
) -> Response:
    """删除 Token；查询日志/统计保留但匿名化（token_id 置 NULL），生词本随级联清理。"""
    token_service.delete_token(db, token_id, admin.id)
    return Response(status_code=204)


@router.get("/{token_id}/vocab-count")
def vocab_count(
    token_id: int, db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)
) -> dict[str, int]:
    return {"count": token_service.get_vocab_count(db, token_id)}
