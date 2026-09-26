"""在线词典查询：维基百科 / 维基词典 / 百度百科 + 外部搜索链接。

参考 myreader-src 的同名实现（app/src/services/dictionaries/providers/）：

- **维基百科**：`{lang}.wikipedia.org` 的 REST summary API（CORS 开放、纯文本 extract）。
- **维基词典**：`en.wiktionary.org` 的 REST definition API；返回的释义是 HTML 片段，
  这里在服务端剥成纯文本——前端按纯文本渲染，第三方 HTML 不进页面，没有注入面。
- **百度百科**：桌面 item 页对非浏览器请求一律弹「百度安全验证」，唯一放行的是
  `/search/word` + Android Chrome 手机 UA（与 myreader/MyBooks 的抓取同款）；
  页面无 CORS 头，浏览器端 fetch 也不许改 User-Agent，所以必须走本服务端中转，
  只取 og: 元信息（标题/描述），不回传原始 HTML。
- **Google / Urban Dictionary / Merriam-Webster / Goodreads**：三家都设
  X-Frame-Options 拒绝内嵌，参考实现的做法是不抓内容、只生成「在外部打开」的
  搜索链接，前端渲染成按钮。

所有出站请求都带超时并并发执行；结果按 (word, lang) 做 10 分钟 TTL 缓存——
这些站点对高频抓取不友好，重复查同一个词没理由再打出去。
"""

import concurrent.futures
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import quote

import httpx
from cachetools import TTLCache

logger = logging.getLogger("mydict.online")

# 单个出站请求的超时：在线结果是「锦上添花」，个别站点慢不能拖垮整个查询
_HTTP_TIMEOUT = 6.0
_FETCH_WORKERS = 3
_CACHE = TTLCache(maxsize=2000, ttl=600)

_BAIKE_NOT_FOUND = "百度百科尚未收录词条"

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")

# Wikimedia 的 UA 政策：要求可识别的描述性 UA（带 Api-User-Agent 头），通用浏览器 UA
# 配代理出口 IP 会被 403（实测）。百度百科则相反，只放行手机浏览器 UA。
_WIKI_HEADERS = {
    "User-Agent": "mydict-dictionary/1.0 (self-hosted dictionary server)",
    "Api-User-Agent": "mydict-dictionary/1.0 (self-hosted dictionary server)",
}
_BAIKE_UA = (
    "Mozilla/5.0 (Linux; U; Android 16;) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/144.0.0.0 Mobile Safari/537.36"
)

# 出站代理：settings.online_dict_proxy，留空直连。lru 拿不到 Settings 实例，
# 由 lookup_online 的调用方注入（端点里从 get_settings() 取）。
_proxy_url: str | None = None


def configure_proxy(proxy_url: str | None) -> None:
    global _proxy_url
    _proxy_url = proxy_url or None
    _CACHE.clear()


def active_proxy() -> str:
    return _proxy_url or ""


def _strip_html(html: str) -> str:
    """把维基词典 REST 接口返回的释义 HTML 片段剥成纯文本。"""
    text = _TAG_RE.sub("", html)
    return _SPACE_RE.sub(" ", unescape(text)).strip()


def _meta(html: str, property_: str) -> str | None:
    match = re.search(
        rf'<meta[^>]+property="{property_}"[^>]+content="([^"]*)"', html
    ) or re.search(rf'<meta[^>]+content="([^"]*)"[^>]+property="{property_}"', html)
    return unescape(match.group(1)) if match else None


def _external_links(word: str) -> list[dict[str, str]]:
    encoded = quote(word)
    return [
        {
            "id": "google",
            "name": "Google",
            "url": f"https://www.google.com/search?q=define:{encoded}&hl=en",
        },
        {
            "id": "urban",
            "name": "Urban Dictionary",
            "url": f"https://www.urbandictionary.com/define.php?term={encoded}",
        },
        {
            "id": "merriam",
            "name": "Merriam-Webster",
            "url": f"https://www.merriam-webster.com/dictionary/{encoded}",
        },
        {
            "id": "goodreads",
            "name": "Goodreads",
            "url": f"https://www.goodreads.com/search?q={encoded}",
        },
    ]


def _fetch_wikipedia(word: str, lang: str) -> dict | None:
    try:
        response = httpx.get(
            f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(word)}",
            headers=_WIKI_HEADERS,
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
            proxy=_proxy_url,
        )
        if response.status_code != 200:
            return None
        data = response.json()
    except Exception:
        logger.warning("Wikipedia 查询失败 %r", word, exc_info=True)
        return None
    extract = (data.get("extract") or "").strip()
    if not extract:
        return None
    return {
        "id": "wikipedia",
        "name": "Wikipedia",
        # titles.display 是 HTML（<span lang=…>苹果</span>），剥成纯文本
        "title": _strip_html((data.get("titles") or {}).get("display") or "")
        or data.get("title")
        or word,
        "subtitle": data.get("description") or "",
        "text": extract,
        "url": (data.get("content_urls") or {}).get("desktop", {}).get("page"),
    }


# 维基词典释义按语言分组；中文词优先取 zh 分区，其余取 en，再退到第一个有内容的
def _pick_wiktionary_lang(data: dict, lang: str) -> list | None:
    for key in ([lang, "en"] if lang != "en" else ["en"]):
        if data.get(key):
            return data[key]
    for value in data.values():
        if value:
            return value
    return None


def _fetch_wiktionary(word: str, lang: str) -> dict | None:
    try:
        response = httpx.get(
            f"https://en.wiktionary.org/api/rest_v1/page/definition/{quote(word)}",
            headers=_WIKI_HEADERS,
            timeout=_HTTP_TIMEOUT,
            proxy=_proxy_url,
        )
        if response.status_code != 200:
            return None
        data = response.json()
    except Exception:
        logger.warning("Wiktionary 查询失败 %r", word, exc_info=True)
        return None
    results = _pick_wiktionary_lang(data, lang)
    if not results:
        return None
    entries = []
    for item in results[:4]:
        senses = []
        for definition in (item.get("definitions") or [])[:8]:
            text = _strip_html(definition.get("definition") or "")
            if not text:
                continue
            examples = [
                _strip_html(example)
                for example in (definition.get("examples") or [])[:3]
            ]
            senses.append(
                {"text": text, "examples": [e for e in examples if e]}
            )
        if senses:
            entries.append(
                {
                    "pos": item.get("partOfSpeech") or "",
                    "language": item.get("language") or "",
                    "senses": senses,
                }
            )
    if not entries:
        return None
    return {"id": "wiktionary", "name": "Wiktionary", "entries": entries}


def _fetch_baike(word: str) -> dict | None:
    try:
        response = httpx.get(
            "https://baike.baidu.com/search/word",
            params={"pic": "1", "enc": "utf-8", "word": word},
            headers={
                "User-Agent": _BAIKE_UA,
                "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.6",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            },
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        )
        if response.status_code != 200:
            return None
        html = response.text
    except Exception:
        logger.warning("百度百科查询失败 %r", word, exc_info=True)
        return None
    if _BAIKE_NOT_FOUND in html or "<title>验证" in html:
        return None
    description = _meta(html, "og:description")
    if not description:
        return None
    title = _meta(html, "og:title") or word
    # doc.title 形如「苹果（蔷薇科苹果属植物）_百度百科」——括号里是简短限定语，
    # 对应维基百科的一行 subtitle
    title_tag = re.search(r"<title>([^<]*)</title>", html)
    descriptor = (
        re.search(r"[（(]([^）)]*)[）)]", unescape(title_tag.group(1))).group(1)
        if title_tag
        else None
    )
    return {
        "id": "baike",
        "name": "百度百科",
        "title": title,
        "subtitle": descriptor or "",
        "text": description,
        "url": str(response.url),
    }


# section 源注册表：id -> 取数函数（统一 (word, lang) 签名，baike 不用 lang）
_SECTION_SOURCES: dict[str, "Any"] = {
    "wikipedia": lambda word, lang: _fetch_wikipedia(word, lang),
    "wiktionary": lambda word, lang: _fetch_wiktionary(word, lang),
    "baike": lambda word, lang: _fetch_baike(word),
}

# 全部可开关的源 id（section 源 + 外链）。管理后台「在线词典」开关的合法取值。
ALL_SOURCE_IDS = frozenset(_SECTION_SOURCES) | {"google", "urban", "merriam", "goodreads"}


def lookup_online(
    word: str, lang: str, enabled_sources: set[str] | None = None
) -> dict:
    """查询在线词典，返回 {word, sections, links}；单个源失败不影响其它源。

    `enabled_sources` 是管理后台「在线词典」开关的白名单（None/空集 = 全部启用），
    id 取值见 ALL_SOURCE_IDS。
    """
    if not enabled_sources:
        enabled_sources = ALL_SOURCE_IDS
    key = (word, lang, tuple(sorted(enabled_sources)))
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    wanted = {sid: fn for sid, fn in _SECTION_SOURCES.items() if sid in enabled_sources}
    with concurrent.futures.ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
        futures = {sid: pool.submit(fn, word, lang) for sid, fn in wanted.items()}
        sections = [f.result() for f in futures.values() if f.result()]

    result = {
        "word": word,
        "lang": lang,
        "sections": sections,
        "links": [
            link for link in _external_links(word) if link["id"] in enabled_sources
        ],
    }
    _CACHE[key] = result
    return result
