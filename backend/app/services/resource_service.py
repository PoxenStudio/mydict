import re
from pathlib import Path

# 匹配 HTML 中 src="..." / href="..." 属性值，排除已是 http(s)://、data: 的外部/内联引用。
_RESOURCE_REF_RE = re.compile(
    r"""(?P<attr>\b(?:src|href)\s*=\s*)(?P<quote>['"])(?!https?://|data:)(?P<path>[^'"]+)(?P=quote)""",
    re.IGNORECASE,
)


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


def rewrite_resource_refs(html: str, dictionary_id: int) -> str:
    """把释义 HTML 中的相对资源引用改写为 /dict-res/{dictionary_id}/res/... 绝对 URL。"""

    def _replace(match: re.Match[str]) -> str:
        try:
            normalized = normalize_resource_path(match.group("path"))
        except ValueError:
            return match.group(0)
        quote = match.group("quote")
        return f"{match.group('attr')}{quote}/dict-res/{dictionary_id}/res/{normalized}{quote}"

    return _RESOURCE_REF_RE.sub(_replace, html)
