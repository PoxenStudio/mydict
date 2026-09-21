"""把词条释义包成一个可在 iframe 里安全渲染的独立 HTML 文档。

为什么不是「净化释义后直接 v-html」：
  - 实测有 11,069,191 条释义带 `<link rel="stylesheet">`，经 innerHTML 注入的 `<link>`
    **会加载并全局生效**（这点与 `<script>` 不同），于是 63 部词典的样式表互相覆盖、
    并把整个应用界面一起改坏；
  - 有 658,154 条带内联事件处理器（onclick/onerror 等），在应用源下会真的执行——
    而前端把 token 存在 localStorage 里，等于把凭证暴露给任意第三方词典文件。

所以改为把释义放进 iframe（sandbox 只给 allow-scripts，不加 allow-same-origin）：
不透明源既保留了各词典自己的 CSS/JS，又拿不到父页面的任何东西。
"""

import re
from functools import lru_cache
from pathlib import Path

# 只给 allow-scripts，与 iframe 的 sandbox 属性保持完全一致。
# 它不额外限制任何子资源加载（所以不会把词典的图片/CSS/字体拦掉），
# 作用是在属性被误删或写错时仍然兜住一层。
_SANDBOX_CSP = "sandbox allow-scripts"

_BOOTSTRAP_PATH = Path(__file__).with_name("iframe_bootstrap.js")

_DOCTYPE_OR_HTML_RE = re.compile(r"^\s*<(?:!doctype|html)\b", re.IGNORECASE)
_HEAD_OPEN_RE = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
_HTML_OPEN_RE = re.compile(r"<html\b[^>]*>", re.IGNORECASE)


@lru_cache(maxsize=1)
def _bootstrap_source() -> str:
    """引导脚本源码；只读一次，避免每个词条请求都读盘。"""
    return _BOOTSTRAP_PATH.read_text(encoding="utf-8")


def _head_snippet(dictionary_id: int) -> str:
    """要插进文档最前面的内容：编码/Referer 策略 + 引导脚本。

    引导脚本必须排在词典自带脚本之前，否则词典脚本一旦先抛错，后面的高度上报、
    链接拦截就都装不上了。
    """
    bootstrap = _bootstrap_source().replace("__MYDICT_DICT_ID__", str(dictionary_id))
    return (
        '<meta charset="utf-8">'
        # 不把本站地址带给出站请求
        '<meta name="referrer" content="no-referrer">'
        f'<meta http-equiv="Content-Security-Policy" content="{_SANDBOX_CSP}">'
        f"<script>{bootstrap}</script>"
    )


def render_entry_document(definition: str, *, dictionary_id: int) -> str:
    """把释义渲染成一个完整 HTML 文档。

    释义本身有可能是完整文档（部分词典的词条带 doctype/html 标签），
    这时不能直接套壳——嵌套 html 会让浏览器进入怪异模式，也会破坏词典自带的 meta。
    改为把引导内容插到它自己的 <head>（或 <html>）之后。
    """
    head = _head_snippet(dictionary_id)

    if _DOCTYPE_OR_HTML_RE.match(definition or ""):
        match = _HEAD_OPEN_RE.search(definition)
        if match is None:
            match = _HTML_OPEN_RE.search(definition)
        if match is not None:
            at = match.end()
            return definition[:at] + head + definition[at:]
        # 既没有 <head> 也没有 <html>，只能在最前面插
        return head + definition

    return (
        "<!DOCTYPE html>"
        '<html lang="zh">'
        f"<head>{head}</head>"
        f"<body>{definition}</body>"
        "</html>"
    )
