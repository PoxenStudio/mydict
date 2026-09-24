"""展开 MDict 的 `` `编号` `` 样式标记。

`.mdx` 头部有一个 `StyleSheet` 字段，词典作者用它定义一批「编号 → 标签」的替换规则，
正文里写 `` `编号` `` 来引用。`mdict_utils` 的 `readmdict.py` 里对它有权威说明：

    stylesheet attribute if present takes form of:
      style_number # 1-255
      style_begin  # or ''
      style_end    # or ''
    store stylesheet in dict in the form of
    {'number' : ('style_begin', 'style_end')}

即**每个编号占三行**：编号、开始标签、结束标记。真实例子（多功能汉语辞典）：

    1
    <b><center><font size=5 color=Green>
    </font></center></b><hr>
    2
    <br>

正文写成 `` `1`不`2``7`◆不`10`bù ㄅㄨˋ`2` ``。

展开规则：**遇到 `` `N` `` 时，先补上一个标记的结束标记，再输出 N 的开始标签**，
并把 N 的结束标记记为待补；文末补上最后那个待补的结束标记。

为什么必须「补上一个的结束」而不是只输出开始标签：`` `1` `` 的开始标签是
`<b><center><font size=5 color=Green>`，只开不关的话 `<center>` 会把**整条词条**都居中加粗；
而 `` `10` `` 这类「开始标签」出现在上一行行尾、它的样式是给下一行正文用的
（`◆不` 红、`bù ㄅㄨˋ` 品红），所以也不能靠「换行即闭合」来偷懒。

编号不在样式表里时该标记原样保留——同库里恰好有几部词典的正文里有反引号数字，
但它们的 mdx 没有 `StyleSheet`（是巧合文本），不能误伤。

是纯文本扫描、不解析 HTML（与 MDict 客户端一致）：理论上 `` `1` `` 若出现在属性值里也会被
展开成标签。真实语料里不存在这种写法（10 万条逐条核过，0 命中），为它加一套属性值区间
判断不划算。
"""

import re
from collections.abc import Mapping

# `` `12` `` 这种标记；\d+ 贪婪匹配，所以 `12` 不会被拆成 `1` + 2`
_MARKER_RE = re.compile(r"`(\d+)`")


def parse_stylesheet(raw: str | None) -> dict[str, tuple[str, str]]:
    """把 `StyleSheet` 字段解析成 `{编号: (开始标签, 结束标记)}`。

    格式是每个编号占三行（编号 / 开始 / 结束），但真实词典里偶尔夹着空行，
    所以这里按「哪一行是纯数字」来定位，而不是像 `readmdict` 那样固定每 3 行取一组——
    遇到畸形数据时只少几条规则，不会越界抛异常。空字段返回空表。
    """
    if not raw:
        return {}
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    sheet: dict[str, tuple[str, str]] = {}
    index = 0
    while index < len(lines):
        number = lines[index].strip()
        if not number.isdigit():
            index += 1
            continue
        begin = lines[index + 1].strip() if index + 1 < len(lines) else ""
        end = lines[index + 2].strip() if index + 2 < len(lines) else ""
        sheet[number] = (begin, end)
        index += 3
    return sheet


def expand_style_markers(text: str, sheet: Mapping[str, tuple[str, str]]) -> str:
    """把正文里的 `` `编号` `` 展开成对应的 HTML 标签。

    没有样式表、没有标记、或标记编号都没定义时原样返回，所以对不依赖这个机制的词典
    （也是绝大多数）是零行为变化。
    """
    if not text or not sheet or "`" not in text:
        return text

    parts: list[str] = []
    pending = ""
    last = 0
    for match in _MARKER_RE.finditer(text):
        rule = sheet.get(match.group(1))
        if rule is None:
            continue  # 编号没定义：原样保留，也不影响「待补」状态
        parts.append(text[last : match.start()])
        parts.append(pending)
        parts.append(rule[0])
        pending = rule[1]
        last = match.end()

    if not parts:
        return text  # 一个都没命中
    parts.append(text[last:])
    parts.append(pending)
    return "".join(parts)


def stylesheet_of(mdx) -> dict[str, tuple[str, str]]:
    """从已打开的 MDX 对象取样式表；没有就返回空表。"""
    header = getattr(mdx, "header", None) or {}
    raw = header.get(b"StyleSheet")
    if not raw:
        return {}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    return parse_stylesheet(raw)
