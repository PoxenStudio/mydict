from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_user
from app.models.user import User
from app.schemas.vocab import VocabCreateRequest, VocabItemOut, VocabListResponse
from app.services import vocab_service

router = APIRouter(prefix="/vocab", tags=["web-vocab"])


@router.get("", response_model=VocabListResponse)
def list_vocab(
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
    lang_from: str | None = None,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> VocabListResponse:
    items, total = vocab_service.list_vocab_items(
        db, "user", user.id, search, page, min(page_size, 100), lang_from
    )
    return VocabListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/languages", response_model=list[str])
def list_languages(user: User = Depends(require_user), db: Session = Depends(get_db)) -> list[str]:
    return vocab_service.list_owner_languages(db, "user", user.id)


@router.post("", response_model=VocabItemOut)
def add_vocab(
    body: VocabCreateRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> VocabItemOut:
    return vocab_service.add_vocab_item(
        db, "user", user.id, body.word, body.dictionary_id, body.note
    )


@router.delete("/{item_id}")
def delete_vocab(
    item_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    vocab_service.delete_vocab_item(db, "user", user.id, item_id)
    return {"ok": True}
