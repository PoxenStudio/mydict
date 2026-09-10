from typing import Literal

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.dictionary import DictEntry
from app.models.vocab import TokenVocabItem, VocabItem
from app.services.query_service import resolve_dictionaries

OwnerKind = Literal["token", "user"]

_MODEL_BY_KIND = {"token": TokenVocabItem, "user": VocabItem}
_OWNER_FIELD_BY_KIND = {"token": "token_id", "user": "user_id"}


def _find_entry(db: Session, word: str, dictionary_id: int | None) -> tuple[DictEntry, int]:
    word_lower = word.strip().lower()
    if dictionary_id is not None:
        entry = (
            db.query(DictEntry)
            .filter(DictEntry.dictionary_id == dictionary_id, DictEntry.word_lower == word_lower)
            .first()
        )
        if entry is None:
            raise NotFoundError("该词典下未找到该单词，无法收藏")
        return entry, dictionary_id

    for dictionary in resolve_dictionaries(db, word):
        entry = (
            db.query(DictEntry)
            .filter(DictEntry.dictionary_id == dictionary.id, DictEntry.word_lower == word_lower)
            .first()
        )
        if entry is not None:
            return entry, dictionary.id
    raise NotFoundError("未找到该单词的释义，无法收藏")


def add_vocab_item(
    db: Session,
    owner_kind: OwnerKind,
    owner_id: int,
    word: str,
    dictionary_id: int | None,
    note: str | None,
):
    entry, resolved_dict_id = _find_entry(db, word, dictionary_id)

    model_cls = _MODEL_BY_KIND[owner_kind]
    owner_field = _OWNER_FIELD_BY_KIND[owner_kind]

    existing = (
        db.query(model_cls)
        .filter(getattr(model_cls, owner_field) == owner_id, model_cls.word == entry.word)
        .first()
    )
    if existing is not None:
        raise ConflictError("已收藏该单词")

    item = model_cls(
        **{owner_field: owner_id},
        word=entry.word,
        dictionary_id=resolved_dict_id,
        phonetic=entry.phonetic,
        definition=entry.definition,
        note=note,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_vocab_items(
    db: Session,
    owner_kind: OwnerKind,
    owner_id: int,
    search: str | None,
    page: int,
    page_size: int,
) -> tuple[list, int]:
    model_cls = _MODEL_BY_KIND[owner_kind]
    owner_field = _OWNER_FIELD_BY_KIND[owner_kind]

    query = db.query(model_cls).filter(getattr(model_cls, owner_field) == owner_id)
    if search:
        query = query.filter(model_cls.word.like(f"%{search.strip()}%"))
    total = query.count()
    items = (
        query.order_by(model_cls.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def delete_vocab_item(db: Session, owner_kind: OwnerKind, owner_id: int, item_id: int) -> None:
    model_cls = _MODEL_BY_KIND[owner_kind]
    owner_field = _OWNER_FIELD_BY_KIND[owner_kind]

    item = db.get(model_cls, item_id)
    if item is None or getattr(item, owner_field) != owner_id:
        raise NotFoundError("生词不存在")
    db.delete(item)
    db.commit()
