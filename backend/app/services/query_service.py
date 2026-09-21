import json
import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser

from sqlalchemy.orm import Session

from app.core import query_cache
from app.models.dictionary import DictEntry, Dictionary
from app.services.query_expand import EXPANSION_VERSION, expand_word

_BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        text = unescape("".join(self._parts))
        lines = [line.strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)


def html_to_plain_text(html: str) -> str:
    parser = _HtmlTextExtractor()
    parser.feed(html)
    parser.close()
    return parser.get_text()


_CJK_RE = re.compile(r"[一-鿿]")

# 输入语言目前只做粗粒度识别（含 CJK 表意文字即视为中文，否则视为英文），不区分简繁；
# 简体/繁体词典的 lang_from 分别存 zh-Hans/zh-Hant（也兼容早期数据用的裸 "zh"），
# 命中中文输入时这三种取值的词典都要能被匹配到，见下方 _ZH_LANG_CODES。
_ZH_LANG_CODES = ("zh", "zh-Hans", "zh-Hant")


def detect_lang(word: str) -> str:
    return "zh" if _CJK_RE.search(word) else "en"


def parse_dict_ids(raw: str | None) -> list[int] | None:
    """解析 `dict=a,b,c` 形式的词典范围参数；空串与无有效数字都视为「不限制」。

    前台与 v1 接口共用同一份解析，避免两边的容错行为不一致。非法项被忽略而不是报错——
    词典可能刚被删掉，用户手里的链接不该因此整条查询失败。
    """
    if not raw:
        return None
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids or None


def filter_existing_dictionary_ids(db: Session, ids: list[int] | None) -> list[int] | None:
    """设置 Token/用户「可用词典」时用来清掉已被删除等不再存在的 id，
    避免限制列表里堆积失效条目；None（不限制）原样透传。空列表等价于不限制——
    "限制到零个词典"不是有意义的可用状态，真要禁用整个 Token/账号应该用状态开关。"""
    if not ids:
        return None
    existing = {row[0] for row in db.query(Dictionary.id).filter(Dictionary.id.in_(ids)).all()}
    filtered = [i for i in ids if i in existing]
    return filtered or None


def _lang_from_values(lang_from: str) -> tuple[str, ...]:
    # 调用方传裸 "zh" 时不区分简繁，等价于自动识别那档的处理；指定 zh-Hans/zh-Hant
    # 则精确匹配到那一种。
    return _ZH_LANG_CODES if lang_from == "zh" else (lang_from,)


def _lang_from_filter(query, lang_from: str):
    return query.filter(Dictionary.lang_from.in_(_lang_from_values(lang_from)))


def _enabled_dictionaries(db: Session, allowed_ids: list[int] | None):
    query = db.query(Dictionary).filter(Dictionary.status == "enabled")
    if allowed_ids is not None:
        query = query.filter(Dictionary.id.in_(allowed_ids))
    return query


def resolve_dictionaries(
    db: Session,
    word: str,
    dict_ids: list[int] | None = None,
    lang_from: str | None = None,
    lang_to: str | None = None,
    allowed_ids: list[int] | None = None,
) -> list[Dictionary]:
    """只返回「优先语言」那批词典（用于前缀建议、收藏时挑一部词典存快照等场景）。

    匹配优先级：显式 dict_ids > 显式 lang_from/lang_to > 按输入文字自动识别语言；
    allowed_ids 非 None 时（Token/用户配置了「可用词典」）在以上任一结果之上再取交集，
    调用方指定的 dict_ids/lang_from 都不能绕过这个限制。
    """
    query = _enabled_dictionaries(db, allowed_ids)
    if dict_ids:
        query = query.filter(Dictionary.id.in_(dict_ids))
    elif lang_from:
        query = _lang_from_filter(query, lang_from)
        if lang_to:
            query = query.filter(Dictionary.lang_to == lang_to)
    else:
        query = _lang_from_filter(query, detect_lang(word))
    return query.order_by(Dictionary.sort_order, Dictionary.id).all()


@dataclass(slots=True)
class CandidateSet:
    """一次查询的候选词典。

    自动识别语言时「优先语言的词典」排前面，「其余语言」作为兜底候选跟在后面；
    显式指定了词典或语言方向时没有兜底候选，两者相同。
    """

    dictionaries: list[Dictionary]
    preferred_ids: frozenset[int]


def resolve_candidates(
    db: Session,
    word: str,
    dict_ids: list[int] | None = None,
    lang_from: str | None = None,
    lang_to: str | None = None,
    allowed_ids: list[int] | None = None,
) -> CandidateSet:
    """解析出候选词典，并标出其中「语言方向与输入一致」的那批。

    为什么要分「优先」与「其余」：`lang_from` 是导入时按采样自动识别的，并不可靠——
    实测用户的 63 部词典里有 6 部中文词典被判成 en（含 46 万条的「汉典」），而原先
    这里是用 lang_from **硬过滤**，判错就等于那部词典的内容永远查不到。改成「先按优先
    语言查，优先语言没有命中再退到其余语言」，判错的词典仍然可达，同时正常情况下
    不会把多语言的无关结果混进来。
    """
    query = _enabled_dictionaries(db, allowed_ids)
    if dict_ids:
        rows = (
            query.filter(Dictionary.id.in_(dict_ids))
            .order_by(Dictionary.sort_order, Dictionary.id)
            .all()
        )
        return CandidateSet(rows, frozenset(d.id for d in rows))
    if lang_from:
        scoped = _lang_from_filter(query, lang_from)
        if lang_to:
            scoped = scoped.filter(Dictionary.lang_to == lang_to)
        rows = scoped.order_by(Dictionary.sort_order, Dictionary.id).all()
        return CandidateSet(rows, frozenset(d.id for d in rows))

    # 自动识别：一次查出全部候选，再在 Python 里分成优先/其余——比两条 SQL 少一次扫描，
    # 词典数量级（几十部）下这点开销可以忽略。
    rows = query.order_by(Dictionary.sort_order, Dictionary.id).all()
    wanted = _lang_from_values(detect_lang(word))
    preferred_ids = frozenset(d.id for d in rows if d.lang_from in wanted)
    preferred = [d for d in rows if d.id in preferred_ids]
    others = [d for d in rows if d.id not in preferred_ids]
    return CandidateSet(preferred + others, preferred_ids)


def list_public_dictionaries(db: Session, allowed_ids: list[int] | None = None) -> list[Dictionary]:
    query = db.query(Dictionary).filter(Dictionary.status == "enabled")
    if allowed_ids is not None:
        query = query.filter(Dictionary.id.in_(allowed_ids))
    return query.order_by(Dictionary.sort_order, Dictionary.id).all()


def _query_entries(
    db: Session, words_lower: list[str], dictionary_ids: list[int]
) -> list[DictEntry]:
    if not dictionary_ids or not words_lower:
        return []
    return (
        db.query(DictEntry)
        .filter(
            DictEntry.dictionary_id.in_(dictionary_ids),
            DictEntry.word_lower.in_(words_lower),
        )
        .all()
    )


def search_word(
    db: Session,
    word: str,
    dict_ids: list[int] | None = None,
    lang_from: str | None = None,
    lang_to: str | None = None,
    allowed_ids: list[int] | None = None,
) -> list[dict]:
    candidates = resolve_candidates(db, word, dict_ids, lang_from, lang_to, allowed_ids)
    if not candidates.dictionaries:
        return []

    word_lower = word.strip().lower()
    # 繁简/全角变体一并查，否则输入简体的用户在只收繁体的词典里永远查不到
    variants = expand_word(word)
    # 缓存 key 必须用**完整候选集**：若只按「优先语言」那批做 key，「优先语言没命中」这个
    # 空结果会被缓存住，兜底路径就永远走不到了。expansion 版本号也要带上，否则改扩展规则后
    # 新结果会被旧缓存挡住。
    cache_key = query_cache.make_key(
        word_lower,
        tuple(d.id for d in candidates.dictionaries),
        f"x{EXPANSION_VERSION}",
    )
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    by_id = {d.id: d for d in candidates.dictionaries}
    preferred = [d.id for d in candidates.dictionaries if d.id in candidates.preferred_ids]
    others = [d.id for d in candidates.dictionaries if d.id not in candidates.preferred_ids]

    entries = _query_entries(db, variants, preferred)
    if not entries:
        # 优先语言一部都没命中，才退到其余语言。命中时绝不混入，避免一次查询把
        # 中/日/英各语言的词典全铺出来。
        entries = _query_entries(db, variants, others)

    # 结果顺序决定前端手风琴里「哪一部默认展开」，所以显式按候选词典的顺序排，
    # 不依赖数据库返回行的顺序。
    order = {d.id: index for index, d in enumerate(candidates.dictionaries)}
    results = [
        {
            "dictionary_id": e.dictionary_id,
            "dictionary_name": by_id[e.dictionary_id].name,
            "word": e.word,
            "phonetic": e.phonetic,
            "definition": e.definition,
            "extra": json.loads(e.extra) if e.extra else None,
            "lang_match": e.dictionary_id in candidates.preferred_ids,
        }
        for e in entries
    ]
    results.sort(key=lambda item: order[item["dictionary_id"]])
    query_cache.set(cache_key, results)
    return results


def get_entry(db: Session, dictionary_id: int, word: str) -> DictEntry | None:
    """取某部词典里的一条词条，供词条 HTML 渲染接口使用。

    不做任何语言/优先级路由：调用方已经指定了「哪部词典的哪个词」，
    这正是查询结果卡片里的那一对。
    """
    return (
        db.query(DictEntry)
        .filter(
            DictEntry.dictionary_id == dictionary_id,
            DictEntry.word_lower == word.strip().lower(),
        )
        .first()
    )


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
