"""外部链接白名单。

`context_url` 这类字段现在只存储、不渲染，但一旦以后被做成可点链接（`<a :href>`、
`window.open`），存进去的 `javascript:` / `data:` 就会在点击时执行。与其等渲染时
再补救，不如写入时就只接受 `http(s)`——危险值压根进不了库。

渲染侧如果将来要加链接，也应调用这里的 `safe_http_url()` 再过一遍（纵深防御）：
数据库里可能还有本次改动之前写入的历史值。
"""

from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}


def safe_http_url(value: str | None) -> str | None:
    """只放行 http/https 且带主机名的绝对 URL，其余一律返回 None。"""
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        return None
    if not parsed.netloc:
        return None
    return candidate
