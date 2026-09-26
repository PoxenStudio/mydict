import json
import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser

from sqlalchemy.orm import Session

from app.core import query_cache
from app.models.dictionary import DictEntry, Dictionary
from app.services.entry_scope import current_generation_only
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

# MDict 用 `@@@LINK=目标词条` 表示「本词条与目标词条同义」，词典制作者拿它做同义词、大小写、
# 简繁变体，以及日语词典里的「見出し語 → 見出し語【読み】」跳转。实测用户库里这类条目有
# 10,505,543 条（占 2468 万词条的 42%），不解析的话用户看到的就是这一行标记本身。
_LINK_RE = re.compile(r"^\s*@@@LINK\s*=\s*(.+?)\s*$", re.IGNORECASE)

# 解引用的最大层数：词典里确实存在 A→B→C 的多级跳转，同时也要防住互相指向的环。
# 只在查询时解引用、不落库，因为多数重定向条目指向的是共享内容——导入时展开会把
# 同一份释义复制上千万份。
_MAX_LINK_DEPTH = 5


def _link_target(definition: str | None) -> str | None:
    """释义是 `@@@LINK=xxx` 时返回目标词头，否则返回 None。"""
    match = _LINK_RE.match(definition or "")
    return match.group(1) if match else None


def _resolve_link(db: Session, entry: DictEntry) -> DictEntry:
    """跟进词条重定向，返回真正承载释义的那条记录。

    只在本词典内跳转——重定向的目标是同一部词典里的另一个词头。链式跳转一路跟到底，
    最多 `_MAX_LINK_DEPTH` 层；目标缺失时原样返回当前这条，让调用方至少还能显示那行标记
    （比空白好排查）。
    """
    current = entry
    seen: set[str] = set()
    for _ in range(_MAX_LINK_DEPTH):
        target = _link_target(current.definition)
        if target is None:
            return current
        key = target.lower()
        if key in seen:  # 环：别再跟了
            return current
        seen.add(key)
        following = (
            current_generation_only(db.query(DictEntry))
            .filter(DictEntry.dictionary_id == entry.dictionary_id, DictEntry.word_lower == key)
            .first()
        )
        if following is None:
            return entry
        current = following
    return current


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
        current_generation_only(db.query(DictEntry))
        .filter(
            DictEntry.dictionary_id.in_(dictionary_ids),
            DictEntry.word_lower.in_(words_lower),
        )
        .all()
    )


# 「精确未命中 → 前缀兜底」时每部词典最多返回的词头数。
_PREFIX_FALLBACK_LIMIT = 8


def _prefix_fallback_entries(
    db: Session, prefix_lower: str, dictionary_id: int
) -> list[DictEntry]:
    """精确匹配打不中时退回到「以输入开头的词头」。

    为什么需要：不少词典的 MDict 词头带注记后缀（Japanese Education Vocabulary 的
    「あ【亜】」「み【味】」、搜韵的「中国【ちゅうごく①】」），对它们做**精确**匹配永远
    打不中，而 MDict 客户端与 django-mdict 的搜索都是前缀式的，用户因此觉得「明明有这部
    词典却查不到」。管理端测试查询本来就是前缀 LIKE（dictionary_service.test_query）。

    查询走 (dictionary_id, word_lower) 复合索引：未命中的词典一次索引范围读，只取前几条，
    代价可忽略；有精确命中的词典根本不进这条路径。
    """
    if not prefix_lower:
        return []
    return (
        current_generation_only(db.query(DictEntry))
        .filter(
            DictEntry.dictionary_id == dictionary_id,
            DictEntry.word_lower.like(f"{prefix_lower}%"),
        )
        .order_by(DictEntry.word_lower)
        .limit(_PREFIX_FALLBACK_LIMIT)
        .all()
    )


def search_word(
    db: Session,
    word: str,
    dict_ids: list[int] | None = None,
    lang_from: str | None = None,
    lang_to: str | None = None,
    allowed_ids: list[int] | None = None,
    *,
    include_definitions: bool = True,
) -> list[dict]:
    """查词。include_definitions=False 时结果里不带释义（前台用：释义另走 /dict/entry）。"""
    candidates = resolve_candidates(db, word, dict_ids, lang_from, lang_to, allowed_ids)
    if not candidates.dictionaries:
        return []

    word_lower = word.strip().lower()
    # 繁简/全角变体一并查，否则输入简体的用户在只收繁体的词典里永远查不到
    variants = expand_word(word)
    # 缓存 key 必须用**完整候选集**：若只按「优先语言」那批做 key，「优先语言没命中」这个
    # 空结果会被缓存住，兜底路径就永远走不到了。expansion 版本号也要带上，否则改扩展规则后
    # 新结果会被旧缓存挡住。带不带释义是两份不同的结果，也要区分开。
    cache_key = query_cache.make_key(
        word_lower,
        tuple(d.id for d in candidates.dictionaries),
        f"x{EXPANSION_VERSION}|d{int(include_definitions)}",
    )
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    by_id = {d.id: d for d in candidates.dictionaries}
    preferred = [d.id for d in candidates.dictionaries if d.id in candidates.preferred_ids]
    others = [d.id for d in candidates.dictionaries if d.id not in candidates.preferred_ids]

    entries = _query_entries(db, variants, preferred)
    if entries:
        # 优先语言有精确命中：其余语言的词典完全不参与（既不精确、也不前缀），
        # 避免一次查询把中/日/英各语言的词典全铺出来。
        fallback_scope = preferred
    else:
        entries = _query_entries(db, variants, others)
        # 其余语言也没命中时两层都试过，前缀兜底放开到全部候选；其余语言有命中时
        # 只在其余语言里兜（优先语言已经精确查过且落空，混进来只会是噪音）。
        fallback_scope = others if entries else preferred + others

    # 前缀兜底：对 fallback_scope 里「精确未命中」的词典退回前缀匹配（词头带注记
    # 后缀的词典，如 Japanese Education Vocabulary 的「あ【亜】」，精确匹配永远打不中）。
    # 上限 _PREFIX_FALLBACK_LIMIT 条/词典，无关语言最多带出可控的几条小噪音。
    hit_ids = {e.dictionary_id for e in entries}
    prefix_entries: list[DictEntry] = []
    for candidate in candidates.dictionaries:
        if candidate.id in hit_ids or candidate.id not in fallback_scope:
            continue
        prefix_entries.extend(
            _prefix_fallback_entries(db, word_lower, candidate.id)
        )
    entries = list(entries) + prefix_entries

    # 结果顺序决定前端手风琴里「哪一部默认展开」，所以显式按候选词典的顺序排，
    # 不依赖数据库返回行的顺序。
    order = {d.id: index for index, d in enumerate(candidates.dictionaries)}
    results = []
    seen_targets: set[tuple[int, int]] = set()
    for e in entries:
        # 释义是 @@@LINK= 时跟进到目标词条取内容；但词头仍显示用户查到的那个，
        # 否则标题行的词会突然变成另一个写法（如「中国」变成「中国【ちゅうごく①】」）
        resolved = _resolve_link(db, e)
        # 同一部词典里几个变体（简繁、大小写）跳到同一个目标时只留一条，否则同一份释义重复出现
        target = (e.dictionary_id, resolved.id)
        if target in seen_targets:
            continue
        seen_targets.add(target)
        item = {
            # 条目主键。同一部词典里可能有**多条同名词条**（MDict 允许），前端拿它做
            # key 与寻址——只用 (dictionary_id, word) 会在这种情况下撞在一起。
            "id": e.id,
            "dictionary_id": e.dictionary_id,
            "dictionary_name": by_id[e.dictionary_id].name,
            "word": e.word,
            "phonetic": resolved.phonetic,
            "extra": json.loads(e.extra) if e.extra else None,
            "lang_match": e.dictionary_id in candidates.preferred_ids,
        }
        if include_definitions:
            item["definition"] = resolved.definition
        results.append(item)
    results.sort(key=lambda item: order[item["dictionary_id"]])
    query_cache.set(cache_key, results)
    return results


def get_entry(db: Session, dictionary_id: int, word: str) -> DictEntry | None:
    """取某部词典里的一条词条，供词条 HTML 渲染接口使用。

    不做任何语言/优先级路由：调用方已经指定了「哪部词典的哪个词」，
    这正是查询结果卡片里的那一对。释义是 `@@@LINK=` 时会跟进到目标词条（见 `_resolve_link`）。
    """
    entry = (
        current_generation_only(db.query(DictEntry))
        .filter(
            DictEntry.dictionary_id == dictionary_id,
            DictEntry.word_lower == word.strip().lower(),
        )
        .first()
    )
    return _resolve_link(db, entry) if entry is not None else None


def get_entries_for_document(
    db: Session,
    dictionary_id: int,
    word: str,
    entry_ids: list[int] | None = None,
) -> list[DictEntry]:
    """取某部词典里与这个词匹配的**全部**词条，按条目 id 排序，供词条 HTML 渲染接口聚合。

    同一部词典里同一词头可以有多条内容不同的条目（MDict 允许，搜韵诗词全文检索版的
    「毛泽东」有 82 条），把它们合成一个文档只要一个 iframe。

    `entry_ids` 给了就按它取——前端把查询结果里那一组的条目 id 显式传过来，保证 iframe 里
    的条数与「共 N 条」一致。无论给没给，都只取词头落在 `expand_word(word)` 变体集合里
    **或以任一变体开头**的条目（与 search_word 的匹配范围一致——搜索有前缀兜底，命中的
    词条词头如「あ【亜】」并不是查询词「あ」的等价变体，而是以它开头）：`entry_ids` 是
    客户端输入，不加这层约束的话随便填 id 就能逐段拉走整部词典，绕过查询配额。

    `entry_ids` 一条都对不上时退回按词取：词典被重新解析后条目 id 整体换新，页面上还开着的
    旧查询结果带的是旧 id，不该因此显示「词条不存在」。

    释义是 `@@@LINK=` 的逐条解引用。
    """
    variants = expand_word(word)
    variants_lower = {variant.lower() for variant in variants}

    def authorized(entry: DictEntry) -> bool:
        """id 归属校验：词条属于目标词典，且词头是查询词的等价变体或以任一变体开头
        （搜索有前缀兜底，命中的词条词头如「あ【亜】」并不是查询词「あ」的变体，
        而是以它开头）。词典归属放在 Python 侧而不是 SQL 里——
        `dictionary_id=? AND id IN (…)` 会让规划器放弃主键、走词典覆盖索引全扫
        （搜韵 826 万行，实测 770ms；纯主键 IN 只要 1ms）。"""
        if entry.dictionary_id != dictionary_id:
            return False
        word_lower = entry.word_lower or ""
        return word_lower in variants_lower or any(
            word_lower.startswith(variant) for variant in variants_lower
        )

    entries: list[DictEntry] = []
    if entry_ids:
        # 纯主键取回（瞬时），归属与词典校验都在 Python 里做——不要把 dictionary_id
        # 塞进这条查询（见 authorized 注释），也不要把十几个前缀 LIKE 塞进一条 OR
        # 查询：都会让规划器放弃索引、退化成整部词典扫描。
        candidates = (
            current_generation_only(db.query(DictEntry))
            .filter(DictEntry.id.in_(entry_ids))
            .order_by(DictEntry.id)
            .all()
        )
        entries = [entry for entry in candidates if authorized(entry)]
    if not entries:
        # 没传 id（或全都不在授权范围内，如词典被重新解析后条目 id 整体换新）时退回按词取
        statement = (
            current_generation_only(db.query(DictEntry))
            .filter(DictEntry.dictionary_id == dictionary_id)
            .filter(DictEntry.word_lower.in_(variants))
        )
        entries = statement.order_by(DictEntry.id).all()
        if not entries:
            # 精确未命中退回前缀（case_sensitive_like=ON 时走索引区间，见 core/db.py）
            statement = (
                current_generation_only(db.query(DictEntry))
                .filter(DictEntry.dictionary_id == dictionary_id)
                .filter(DictEntry.word_lower.like(f"{word.strip().lower()}%"))
            )
            entries = statement.order_by(DictEntry.id).all()
    # 几条跳到同一个目标的只留一份（与 search_word 的去重一致，条数才对得上「共 N 条」）
    resolved: dict[int, DictEntry] = {}
    for entry in entries:
        target = _resolve_link(db, entry)
        resolved.setdefault(target.id, target)
    return list(resolved.values())


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
        current_generation_only(db.query(DictEntry.word))
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
