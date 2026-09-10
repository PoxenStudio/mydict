from typing import Literal

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.dictionary import DictEntry, Dictionary
from app.models.vocab import TokenVocabItem, VocabItem
from app.services.query_service import resolve_dictionaries
from app.services.settings_service import get_setting

OwnerKind = Literal["token", "user"]

_MODEL_BY_KIND = {"token": TokenVocabItem, "user": VocabItem}
_OWNER_FIELD_BY_KIND = {"token": "token_id", "user": "user_id"}


def _max_items_per_owner(db: Session) -> int | None:
    raw = get_setting(db, "vocab_max_items_per_owner")
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


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

    max_items = _max_items_per_owner(db)
    if max_items is not None:
        current_count = (
            db.query(model_cls).filter(getattr(model_cls, owner_field) == owner_id).count()
        )
        if current_count >= max_items:
            raise ConflictError(f"生词本已达上限（{max_items} 条）")

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
    lang_from: str | None = None,
) -> tuple[list, int]:
    model_cls = _MODEL_BY_KIND[owner_kind]
    owner_field = _OWNER_FIELD_BY_KIND[owner_kind]

    query = db.query(model_cls).filter(getattr(model_cls, owner_field) == owner_id)
    if search:
        query = query.filter(model_cls.word.like(f"%{search.strip()}%"))
    if lang_from:
        query = query.join(Dictionary, model_cls.dictionary_id == Dictionary.id).filter(
            Dictionary.lang_from == lang_from
        )
    total = query.count()
    items = (
        query.order_by(model_cls.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def list_owner_languages(db: Session, owner_kind: OwnerKind, owner_id: int) -> list[str]:
    """生词本里出现过的来源词典语言（去重），供前台按语言分 tab 展示可切换的类别。"""
    model_cls = _MODEL_BY_KIND[owner_kind]
    owner_field = _OWNER_FIELD_BY_KIND[owner_kind]
    rows = (
        db.query(Dictionary.lang_from)
        .join(model_cls, model_cls.dictionary_id == Dictionary.id)
        .filter(getattr(model_cls, owner_field) == owner_id)
        .distinct()
        .all()
    )
    return sorted({row[0] for row in rows})


def delete_vocab_item(db: Session, owner_kind: OwnerKind, owner_id: int, item_id: int) -> None:
    model_cls = _MODEL_BY_KIND[owner_kind]
    owner_field = _OWNER_FIELD_BY_KIND[owner_kind]

    item = db.get(model_cls, item_id)
    if item is None or getattr(item, owner_field) != owner_id:
        raise NotFoundError("生词不存在")
    db.delete(item)
    db.commit()
