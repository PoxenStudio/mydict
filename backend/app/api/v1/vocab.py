from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_api_token
from app.models.token import ApiToken
from app.schemas.vocab import VocabCreateRequest, VocabItemOut, VocabListResponse
from app.services import vocab_service

router = APIRouter(prefix="/v1/vocab", tags=["v1-vocab"])


@router.get("", response_model=VocabListResponse)
def list_vocab(
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
    token: ApiToken = Depends(require_api_token),
    db: Session = Depends(get_db),
) -> VocabListResponse:
    items, total = vocab_service.list_vocab_items(
        db, "token", token.id, search, page, min(page_size, 100)
    )
    return VocabListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=VocabItemOut)
def add_vocab(
    body: VocabCreateRequest,
    token: ApiToken = Depends(require_api_token),
    db: Session = Depends(get_db),
) -> VocabItemOut:
    return vocab_service.add_vocab_item(
        db, "token", token.id, body.word, body.dictionary_id, body.note
    )


@router.delete("/{item_id}")
def delete_vocab(
    item_id: int,
    token: ApiToken = Depends(require_api_token),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    vocab_service.delete_vocab_item(db, "token", token.id, item_id)
    return {"ok": True}
