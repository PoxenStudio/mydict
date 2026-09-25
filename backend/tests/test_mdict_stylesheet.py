"""` `编号` ` 样式标记展开的用例。

替换规则的来源与论证见 `app/parsers/mdict_stylesheet.py` 的模块注释：核心是「遇到标记时先补
上一个标记的结束标记，再输出当前的开始标签」，否则 `` `1` `` 的 `<center>` 只开不关会把整条
词条都居中加粗。
"""

import pytest

from app.parsers.mdict_stylesheet import (
    expand_style_markers,
    parse_stylesheet,
    stylesheet_of,
)

# 真实词典（多功能汉语辞典）的样式表片段，编号刻意不连续
RAW = "\n".join(
    [
        "1",
        "<b><center><font size=5 color=Green>",
        "</font></center></b><hr>",
        "2",
        "<br>",
        "",
        "7",
        "<font color=Red>",
        "</font>",
        "10",
        "<font color=Fuchsia>",
        "</font>",
        "13",
        "",
        "",
    ]
)


def test_parse_stylesheet_groups_number_with_begin_and_end() -> None:
    sheet = parse_stylesheet(RAW)
    assert sheet["1"] == ("<b><center><font size=5 color=Green>", "</font></center></b><hr>")
    assert sheet["2"] == ("<br>", "")
    assert sheet["7"] == ("<font color=Red>", "</font>")
    # 编号不连续也要各就各位：13 的开始与结束都是空串（作者用它表示「无样式」）
    assert sheet["13"] == ("", "")
    assert set(sheet) == {"1", "2", "7", "10", "13"}


@pytest.mark.parametrize("raw", [None, "", "\n\n"])
def test_parse_stylesheet_returns_empty_for_blank(raw: str | None) -> None:
    assert parse_stylesheet(raw) == {}


def test_parse_stylesheet_tolerates_crlf() -> None:
    assert parse_stylesheet(RAW.replace("\n", "\r\n")) == parse_stylesheet(RAW)


def test_parse_stylesheet_stops_at_truncated_tail() -> None:
    """末尾少一两行（畸形数据）不该抛异常，只是少几条规则。"""
    assert parse_stylesheet("1\n<b>") == {"1": ("<b>", "")}


def test_expand_closes_previous_marker_before_opening_next() -> None:
    """`` `1` `` 与 `` `7` `` 相邻时，1 的结束标记必须出现在 7 的开始标签之前。"""
    out = expand_style_markers("`1`不`7`◆不", parse_stylesheet(RAW))
    assert out == (
        "<b><center><font size=5 color=Green>不"
        "</font></center></b><hr>"
        "<font color=Red>◆不</font>"
    )


def test_expand_uses_marker_beginning_at_line_end_for_next_line() -> None:
    """`` `10` `` 出现在上一行行尾、它的样式是给下一行正文用的，不能靠换行闭合。"""
    out = expand_style_markers("◆不`10`bù ㄅㄨˋ`2`", parse_stylesheet(RAW))
    assert out == "◆不<font color=Fuchsia>bù ㄅㄨˋ</font><br>"


def test_expand_appends_trailing_end_marker() -> None:
    out = expand_style_markers("`7`红字", parse_stylesheet(RAW))
    assert out == "<font color=Red>红字</font>"


def test_expand_is_idempotent(self_check: str = "") -> None:
    """展开过之后文本里不再有已定义的编号，第二次跑应当一行都不改——这是存量修复能
    安全重复执行的前提。"""
    sheet = parse_stylesheet(RAW)
    once = expand_style_markers("`1`不`2``7`◆不`10`bù`2`", sheet)
    assert expand_style_markers(once, sheet) == once


def test_expand_keeps_undefined_numbers_verbatim() -> None:
    """编号不在样式表里时原样保留：同库里有几部词典的正文恰好含反引号数字，但它们的
    mdx 没有 StyleSheet，是巧合文本，绝不能动。"""
    sheet = parse_stylesheet(RAW)
    assert expand_style_markers("`99`未知`1`已知", sheet) == (
        "`99`未知<b><center><font size=5 color=Green>已知</font></center></b><hr>"
    )


def test_expand_returns_original_text_when_nothing_matches() -> None:
    sheet = parse_stylesheet(RAW)
    for text in ["", "普通文本", "`99`全是未定义"]:
        assert expand_style_markers(text, sheet) == text


def test_expand_returns_original_text_without_stylesheet() -> None:
    text = "`1`不`2`"
    assert expand_style_markers(text, {}) == text


class _FakeMdx:
    def __init__(self, header: dict[bytes, bytes]) -> None:
        self.header = header


def test_stylesheet_of_reads_bytes_header() -> None:
    assert stylesheet_of(_FakeMdx({b"StyleSheet": RAW.encode()}))["2"] == ("<br>", "")


@pytest.mark.parametrize(
    "header",
    [{}, {b"StyleSheet": b""}, None],
)
def test_stylesheet_of_returns_empty_when_absent(header: dict[bytes, bytes] | None) -> None:
    assert stylesheet_of(_FakeMdx(header)) == {}
