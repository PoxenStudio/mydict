import json
import re

from sqlalchemy.orm import Session

from app.core import query_cache
from app.models.dictionary import DictEntry, Dictionary

_CJK_RE = re.compile(r"[一-鿿]")


def detect_lang(word: str) -> str:
    return "zh" if _CJK_RE.search(word) else "en"


def resolve_dictionaries(
    db: Session, word: str, dict_ids: list[int] | None = None
) -> list[Dictionary]:
    """按输入语言自动匹配已启用词典（同一 lang_from 的多部词典并列返回），
    也可用 dict_ids 显式指定。"""
    query = db.query(Dictionary).filter(Dictionary.status == "enabled")
    if dict_ids:
        query = query.filter(Dictionary.id.in_(dict_ids))
    else:
        query = query.filter(Dictionary.lang_from == detect_lang(word))
    return query.order_by(Dictionary.sort_order, Dictionary.id).all()


def list_public_dictionaries(db: Session) -> list[Dictionary]:
    return (
        db.query(Dictionary)
        .filter(Dictionary.status == "enabled")
        .order_by(Dictionary.sort_order, Dictionary.id)
        .all()
    )


def search_word(db: Session, word: str, dict_ids: list[int] | None = None) -> list[dict]:
    dictionaries = resolve_dictionaries(db, word, dict_ids)
    if not dictionaries:
        return []

    word_lower = word.strip().lower()
    cache_key = query_cache.make_key(word_lower, tuple(d.id for d in dictionaries))
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    by_id = {d.id: d for d in dictionaries}
    entries = (
        db.query(DictEntry)
        .filter(DictEntry.dictionary_id.in_(by_id.keys()), DictEntry.word_lower == word_lower)
        .all()
    )
    results = [
        {
            "dictionary_id": e.dictionary_id,
            "dictionary_name": by_id[e.dictionary_id].name,
            "word": e.word,
            "phonetic": e.phonetic,
            "definition": e.definition,
            "extra": json.loads(e.extra) if e.extra else None,
        }
        for e in entries
    ]
    query_cache.set(cache_key, results)
    return results


def suggest_prefix(
    db: Session, prefix: str, dict_ids: list[int] | None = None, limit: int = 10
) -> list[str]:
    dictionaries = resolve_dictionaries(db, prefix, dict_ids)
    if not dictionaries:
        return []
    prefix_lower = prefix.strip().lower()
    rows = (
        db.query(DictEntry.word)
        .filter(
            DictEntry.dictionary_id.in_([d.id for d in dictionaries]),
            DictEntry.word_lower.like(f"{prefix_lower}%"),
        )
        .order_by(DictEntry.word_lower)
        .limit(limit * 3)
        .all()
    )
    seen: set[str] = set()
    words: list[str] = []
    for (w,) in rows:
        if w in seen:
            continue
        seen.add(w)
        words.append(w)
        if len(words) >= limit:
            break
    return words
