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
    # 原始控制字符（\r\n\t NUL 等）：真实浏览器给的 location.href 是百分号编码过的，
    # 出现裸控制字符只可能是构造出来的——既可能是 CRLF 注入，也可能是解析歧义，直接拒。
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in candidate):
        return None
    # 反斜杠：浏览器（WHATWG）对 http(s) 会把 `\` 当 `/` 归一化，服务端按 RFC 解析却是
    # 普通字符——两边对 host 的理解会不一致（`https://\javascript:...` 就是钻这个空子）。
    # 真实 location.href 不会出现裸反斜杠，直接拒掉。
    if "\\" in candidate:
        return None
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        return None
    # 同时要求 netloc 与 hostname：netloc 只排掉「冒号后没有 //」这一类比，
    # `http://user@`、`https://\javascript:...` 这类 netloc 非空但没有合法主机的仍能混过去。
    if not parsed.netloc or not parsed.hostname:
        return None
    return candidate
