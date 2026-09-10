import json
import re

from sqlalchemy.orm import Session

from app.core import query_cache
from app.models.dictionary import DictEntry, Dictionary

_CJK_RE = re.compile(r"[一-鿿]")

# 输入语言目前只做粗粒度识别（含 CJK 表意文字即视为中文，否则视为英文），不区分简繁；
# 简体/繁体词典的 lang_from 分别存 zh-Hans/zh-Hant（也兼容早期数据用的裸 "zh"），
# 命中中文输入时这三种取值的词典都要能被匹配到，见下方 _ZH_LANG_CODES。
_ZH_LANG_CODES = ("zh", "zh-Hans", "zh-Hant")


def detect_lang(word: str) -> str:
    return "zh" if _CJK_RE.search(word) else "en"


def filter_existing_dictionary_ids(db: Session, ids: list[int] | None) -> list[int] | None:
    """设置 Token/用户「可用词典」时用来清掉已被删除等不再存在的 id，
    避免限制列表里堆积失效条目；None（不限制）原样透传。空列表等价于不限制——
    "限制到零个词典"不是有意义的可用状态，真要禁用整个 Token/账号应该用状态开关。"""
    if not ids:
        return None
    existing = {row[0] for row in db.query(Dictionary.id).filter(Dictionary.id.in_(ids)).all()}
    filtered = [i for i in ids if i in existing]
    return filtered or None


def _lang_from_filter(query, lang_from: str):
    # 调用方传裸 "zh" 时不区分简繁，等价于自动识别那档的处理；指定 zh-Hans/zh-Hant
    # 则精确匹配到那一种。
    if lang_from == "zh":
        return query.filter(Dictionary.lang_from.in_(_ZH_LANG_CODES))
    return query.filter(Dictionary.lang_from == lang_from)


def resolve_dictionaries(
    db: Session,
    word: str,
    dict_ids: list[int] | None = None,
    lang_from: str | None = None,
    lang_to: str | None = None,
    allowed_ids: list[int] | None = None,
) -> list[Dictionary]:
    """匹配词典优先级：显式 dict_ids > 显式 lang_from/lang_to > 按输入文字自动识别语言；
    allowed_ids 非 None 时（Token/用户配置了「可用词典」）在以上任一结果之上再取交集，
    调用方指定的 dict_ids/lang_from 都不能绕过这个限制。"""
    query = db.query(Dictionary).filter(Dictionary.status == "enabled")
    if allowed_ids is not None:
        query = query.filter(Dictionary.id.in_(allowed_ids))
    if dict_ids:
        query = query.filter(Dictionary.id.in_(dict_ids))
    elif lang_from:
        query = _lang_from_filter(query, lang_from)
        if lang_to:
            query = query.filter(Dictionary.lang_to == lang_to)
    else:
        query = _lang_from_filter(query, detect_lang(word))
    return query.order_by(Dictionary.sort_order, Dictionary.id).all()


def list_public_dictionaries(
    db: Session, allowed_ids: list[int] | None = None
) -> list[Dictionary]:
    query = db.query(Dictionary).filter(Dictionary.status == "enabled")
    if allowed_ids is not None:
        query = query.filter(Dictionary.id.in_(allowed_ids))
    return query.order_by(Dictionary.sort_order, Dictionary.id).all()


def search_word(
    db: Session,
    word: str,
    dict_ids: list[int] | None = None,
    lang_from: str | None = None,
    lang_to: str | None = None,
    allowed_ids: list[int] | None = None,
) -> list[dict]:
    dictionaries = resolve_dictionaries(db, word, dict_ids, lang_from, lang_to, allowed_ids)
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
    db: Session,
    prefix: str,
    dict_ids: list[int] | None = None,
    limit: int = 10,
    allowed_ids: list[int] | None = None,
) -> list[str]:
    dictionaries = resolve_dictionaries(db, prefix, dict_ids, allowed_ids=allowed_ids)
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
