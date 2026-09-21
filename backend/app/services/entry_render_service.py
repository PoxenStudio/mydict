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

# 主题只认这两个值，其它输入一律当作「没指定」
_THEMES = frozenset({"light", "dark"})

# 暗色适配样式。词典原文常把颜色写死（白底黑字），在暗色主题下十分刺眼；这里只翻
# 「明确写着黑/白」的那部分呈现，词典自带的红字、彩色表格等语义色一律保留——正因为要
# 保留语义色，才不能写成 `* { color: ... !important }` 的通配覆盖，那会把它们一起抹平。
#
# 选择器全部门控在 html[data-mydict-theme='dark'] 之下，浅色主题时整段样式是惰性的，
# 因此不需要按主题生成两份 CSS。
#
# 属性挂在 html 而不是 body 上：body 可能被词典自己定义，我们只加属性，不跟它抢样式。
#
# 颜色值与前端的 styles/tokens/color.css 里 `:root[data-theme='dark']
# --color-text-primary` 保持一致——iframe 是不透明源，读不到父页的 CSS 变量，
# 只能把值镜像成字面量，改前端 token 时这里要一起改。
_THEME_STYLE = (
    "<style>"
    "html[data-mydict-theme='dark']{color-scheme:dark;background-color:transparent}"
    # 正文默认色：词典没写颜色的文字继承这里，写了黑色的由下面两条覆盖
    "html[data-mydict-theme='dark'] body{background-color:transparent;color:#eaf1ee}"
    # <font color> / bgcolor 这类表现属性本身优先级低于作者样式表，不必加 !important。
    # #000 与 #000000 是精确匹配，必须分别列出。
    "html[data-mydict-theme='dark'] [color='#000' i],"
    "html[data-mydict-theme='dark'] [color='#000000' i],"
    "html[data-mydict-theme='dark'] [color='black' i]{color:#eaf1ee}"
    # 内联 style 优先级最高，必须 !important 才盖得住；子串 color:#000 已含 color:#000000
    "html[data-mydict-theme='dark'] [style*='color:#000' i],"
    "html[data-mydict-theme='dark'] [style*='color: #000' i],"
    "html[data-mydict-theme='dark'] [style*='color:black' i],"
    "html[data-mydict-theme='dark'] [style*='color: black' i],"
    "html[data-mydict-theme='dark'] [style*='color:rgb(0,0,0)' i],"
    "html[data-mydict-theme='dark'] [style*='color: rgb(0, 0, 0)' i]{color:#eaf1ee !important}"
    # 白底转透明，自然透出父页的暗色表面（EntryFrame 已把 iframe 背景设为 transparent）
    "html[data-mydict-theme='dark'] [bgcolor='#fff' i],"
    "html[data-mydict-theme='dark'] [bgcolor='#ffffff' i],"
    "html[data-mydict-theme='dark'] [bgcolor='white' i],"
    "html[data-mydict-theme='dark'] [style*='background:#fff' i],"
    "html[data-mydict-theme='dark'] [style*='background: #fff' i],"
    "html[data-mydict-theme='dark'] [style*='background-color:#fff' i],"
    "html[data-mydict-theme='dark'] [style*='background-color: #fff' i],"
    "html[data-mydict-theme='dark'] [style*='background:white' i],"
    "html[data-mydict-theme='dark'] [style*='background: white' i]"
    "{background-color:transparent !important}"
    "</style>"
)

# 选中词条里的文字时弹出的【查词】按钮样式。
#
# 刻意与 _THEME_STYLE 分开：那份有「不能出现 <html>/<body>/<!doctype 字面量」的断言，
# 混在一起以后加菜单样式容易误踩；而且它只在允许查词的渲染路径上注入，生词本与管理端
# 拿到的文档保持与之前字节级一致。
#
# 定位用 fixed：fixed 元素不参与 scrollHeight，所以菜单不会把词条高度顶大——高度上报是
# iframe 的命脉，不能让它干扰。
_LOOKUP_STYLE = (
    "<style>"
    ".mydict-lookup{position:fixed;z-index:2147483647;padding:4px 12px;border-radius:6px;"
    "font-size:13px;line-height:1.7;cursor:pointer;user-select:none;-webkit-user-select:none;"
    "white-space:nowrap;background:#fff;color:#0f2b22;border:1px solid #d8e2de;"
    "box-shadow:0 4px 14px rgba(0,0,0,.16);"
    "font-family:system-ui,-apple-system,'PingFang SC','Microsoft YaHei',sans-serif}"
    "[data-mydict-theme='dark'] .mydict-lookup{background:#1c2a25;color:#eaf1ee;"
    "border-color:#33443d;box-shadow:0 4px 14px rgba(0,0,0,.5)}"
    "</style>"
)

_DOCTYPE_OR_HTML_RE = re.compile(r"^\s*<(?:!doctype|html)\b", re.IGNORECASE)
_HEAD_OPEN_RE = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
_HTML_OPEN_RE = re.compile(r"<html\b[^>]*>", re.IGNORECASE)


@lru_cache(maxsize=1)
def _bootstrap_source() -> str:
    """引导脚本源码；只读一次，避免每个词条请求都读盘。"""
    return _BOOTSTRAP_PATH.read_text(encoding="utf-8")


def _theme_init_script(theme: str | None) -> str:
    """把主题属性直接写进文档，消掉「先按系统偏好渲染、等父页消息到达才变色」的那次闪变。

    未指定主题时返回空串：交给引导脚本按系统偏好兜底，父页之后仍可通过 mydict:cmd 纠正。
    """
    if theme not in _THEMES:
        return ""
    return f"<script>document.documentElement.setAttribute('data-mydict-theme','{theme}')</script>"


def _head_snippet(
    dictionary_id: int, theme: str | None = None, allow_lookup: bool = False
) -> str:
    """要插进文档最前面的内容：编码/Referer 策略 + 主题初值 + 样式 + 引导脚本。

    引导脚本必须排在词典自带脚本之前，否则词典脚本一旦先抛错，后面的高度上报、
    链接拦截就都装不上了。样式排在引导脚本之前：它不依赖脚本，早一步应用就少一帧白闪。

    allow_lookup 为真时额外注入选中查词的菜单样式，并把开关告诉引导脚本。
    """
    bootstrap = (
        _bootstrap_source()
        .replace("__MYDICT_DICT_ID__", str(dictionary_id))
        .replace("__MYDICT_LOOKUP__", "true" if allow_lookup else "false")
    )
    lookup_style = _LOOKUP_STYLE if allow_lookup else ""
    return (
        '<meta charset="utf-8">'
        # 不把本站地址带给出站请求
        '<meta name="referrer" content="no-referrer">'
        f'<meta http-equiv="Content-Security-Policy" content="{_SANDBOX_CSP}">'
        f"{_theme_init_script(theme)}"
        f"{_THEME_STYLE}"
        f"{lookup_style}"
        f"<script>{bootstrap}</script>"
    )


def render_entry_document(
    definition: str,
    *,
    dictionary_id: int,
    theme: str | None = None,
    allow_lookup: bool = False,
) -> str:
    """把释义渲染成一个完整 HTML 文档。

    释义本身有可能是完整文档（部分词典的词条带 doctype/html 标签），
    这时不能直接套壳——嵌套 html 会让浏览器进入怪异模式，也会破坏词典自带的 meta。
    改为把引导内容插到它自己的 <head>（或 <html>）之后。

    theme 为 'light'/'dark' 时把主题写死在文档里（首屏零闪变）；为 None 时交给子页
    按系统偏好决定，父页之后仍可通过 mydict:cmd 下发纠正。

    allow_lookup 只在**前台查询页**那条路径上传 True：选中文字弹【查词】需要有地方接住
    这个查询（最后由 iframe 发 mydict:entry 消息、父页发起新查询）。生词本与管理端预览
    没有查词框，传 False 让它们连菜单都不出现。
    """
    head = _head_snippet(dictionary_id, theme, allow_lookup)

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
