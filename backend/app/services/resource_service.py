import re
from pathlib import Path

# 匹配 HTML 中 src="..." / href="..." 属性值。
# 负向前瞻一口气跳过所有「不该改写」的引用，避免每条外部链接都要进一次 Python 回调——
# 释义里绝大多数资源引用都是 http(s)/data:，这个跳过是热路径上的主要优化。
#   entry://  MDict 的词条内跳转协议，指向另一条词条而不是文件，交给前端点击时拦截
#   #       页内锚点
#   //      、www. 协议相对/裸域名的外链
#   javascript: / file: 一律原样保留（前端会拦截点击，绝不把它改成可执行的样子）
_RESOURCE_REF_RE = re.compile(
    r"""(?P<attr>\b(?:src|href)\s*=\s*)(?P<quote>['"])(?P<path>[^'"]+)(?P=quote)""",
    re.IGNORECASE,
)

# 这些前缀开头的引用原样保留。放在 lookahead 里比在回调里判断更快。
_SKIP_PREFIX_RE = re.compile(
    r"^(?:https?://|data:|entry://|#|//|www\.|mailto:|javascript:|file:|ftp://|blob:|tel:)",
    re.IGNORECASE,
)

# sound:// 是 MDict 的音频引用协议，指向 .mdd 里解包出来的音频文件，需要改写成可播放的 URL。
_SOUND_PREFIX_RE = re.compile(r"^sound://", re.IGNORECASE)

# 「带 scheme」的通用判据：字母开头 + 若干合法字符 + 冒号。
# 放在 sound:// 之后判断，用来把其它未知协议（ws://、自定义协议等）保守地原样留下。
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


def normalize_resource_path(raw_path: str) -> str:
    """把词典内部的资源相对路径规范化为正斜杠、去掉开头分隔符，拒绝路径穿越。"""
    path = raw_path.replace("\\", "/").lstrip("/")
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError(f"resource path traversal rejected: {raw_path!r}")
    return "/".join(parts)


def write_resource(resource_dir: Path, relative_path: str, content: bytes) -> None:
    """将资源内容写入 resource_dir/relative_path，自动创建父目录。"""
    normalized = normalize_resource_path(relative_path)
    target = resource_dir / normalized
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def _split_suffix(raw: str) -> tuple[str, str]:
    """把 ?query 与 #fragment 从路径里拆出来，返回 (路径, 后缀)。"""
    path, sep, fragment = raw.partition("#")
    path, qsep, query = path.partition("?")
    suffix = ""
    if qsep:
        suffix = "?" + query
    if sep:
        suffix += "#" + fragment
    return path, suffix


def _to_resource_url(raw: str, dictionary_id: int) -> str | None:
    """把资源相对路径拼成 /dict-res/ 绝对 URL；无法规范化（越权等）时返回 None。"""
    path, suffix = _split_suffix(raw)
    try:
        normalized = normalize_resource_path(path)
    except ValueError:
        return None
    if not normalized:
        return None
    return f"/dict-res/{dictionary_id}/res/{normalized}{suffix}"


def _rewrite_value(raw: str, dictionary_id: int) -> str:
    """单条属性值的改写规则；返回原值时表示「不改写」。"""
    if _SKIP_PREFIX_RE.match(raw):
        return raw

    # sound://audio/x.spx -> /dict-res/{id}/res/audio/x.spx，前端据此播放
    if _SOUND_PREFIX_RE.match(raw):
        return _to_resource_url(_SOUND_PREFIX_RE.sub("", raw), dictionary_id) or raw

    # 其余任何带 scheme 的引用都不属于「词典内部资源」，保守留下
    if _SCHEME_RE.match(raw):
        return raw

    # 无扩展名的裸相对路径在 MDX 里基本都是词条链接（entry:// 的简写），
    # 补成 /dict-res/ 只会得到一个 404 —— 这里不动它。
    head = raw.split("#", 1)[0].split("?", 1)[0]
    if "." not in head.rsplit("/", 1)[-1]:
        return raw

    return _to_resource_url(raw, dictionary_id) or raw


def rewrite_resource_refs(html: str, dictionary_id: int) -> str:
    """把释义 HTML 中的相对资源引用改写为 /dict-res/{dictionary_id}/res/... 绝对 URL。

    entry:// 词条链接与外部链接原样保留：前者由前端点击时拦截并发起新查询，
    后者本就该指向站外。
    """

    def _replace(match: re.Match[str]) -> str:
        value = match.group("path")
        rewritten = _rewrite_value(value, dictionary_id)
        if rewritten == value:
            return match.group(0)
        quote = match.group("quote")
        return f"{match.group('attr')}{quote}{rewritten}{quote}"

    return _RESOURCE_REF_RE.sub(_replace, html)
