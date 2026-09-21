from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_user
from app.models.user import User
from app.schemas.vocab import VocabCreateRequest, VocabItemOut, VocabListResponse
from app.services import vocab_service
from app.services.entry_render_service import render_entry_document

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


@router.get("/{item_id}/entry", response_class=HTMLResponse)
def vocab_entry_document(
    item_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """把生词本里保存的释义**快照**渲染成隔离 iframe 用的 HTML 文档。

    刻意渲染快照而不是按词典实时取：生词本存的就是收藏当时那份释义，词典后来被删除或
    修改都不该影响它——实时取会在这两种情况下直接渲染失败。快照里的资源引用在导入时
    就已改写成 /dict-res/{id}/res/ 绝对地址，所以只要词典还在，图片发音照常能显示。
    """
    item = vocab_service.get_vocab_item(db, "user", user.id, item_id)
    return HTMLResponse(
        render_entry_document(item.definition or "", dictionary_id=item.dictionary_id or 0)
    )


@router.delete("/{item_id}")
def delete_vocab(
    item_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    vocab_service.delete_vocab_item(db, "user", user.id, item_id)
    return {"ok": True}
