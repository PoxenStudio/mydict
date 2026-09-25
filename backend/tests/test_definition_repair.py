"""一次性修复命令的用例。

修复代码修好之后，正常的导入路径已经不会再产出坏链接了，所以这里**手工构造遗留行**
（形如 /dict-res/{id}/res/entry:/... 、/sound:/... 与 /file:/...），模拟修复前入库的数据。
"""

from sqlalchemy.orm import Session

from app.models.dictionary import DictEntry, Dictionary
from app.services.definition_repair import (
    count_legacy_links,
    dictionaries_using_style_markers,
    expand_stored_styles,
    repair_legacy_links,
)
from app.services.resource_service import rewrite_resource_refs


def _make_dictionary(db: Session, name: str = "测试词典") -> Dictionary:
    dictionary = Dictionary(
        name=name,
        format="mdict",
        lang_from="zh-Hans",
        lang_to="zh-Hans",
        file_path="/data/dicts/test.mdx",
        status="enabled",
    )
    db.add(dictionary)
    db.commit()
    return dictionary


def _add_entry(db: Session, dictionary_id: int, word: str, definition: str) -> DictEntry:
    entry = DictEntry(
        dictionary_id=dictionary_id,
        word=word,
        word_lower=word.lower(),
        definition=definition,
        extra=None,
    )
    db.add(entry)
    db.commit()
    return entry


def _legacy(dictionary_id: int, original: str) -> str:
    """复现旧版改写的行为，用来构造遗留数据。"""
    base = f"/dict-res/{dictionary_id}/res/"
    return (
        original.replace("entry://", base + "entry:/")
        .replace("sound://", base + "sound:/")
        .replace('src="file:///', f'src="{base}file:/')
        .replace('src="pic/', f'src="{base}pic/')
    )


def _definition(db: Session, entry_id: int) -> str:
    db.expire_all()
    return db.get(DictEntry, entry_id).definition


def test_repair_fixes_entry_and_sound_links(db_session: Session) -> None:
    did = _make_dictionary(db_session).id
    entry = _add_entry(
        db_session,
        did,
        "苹果",
        f'<a href="/dict-res/{did}/res/entry:/苹果">苹果</a>'
        f'<a href="/dict-res/{did}/res/sound:/audio/guo.spx">🔊</a>',
    )

    repaired = repair_legacy_links(db_session, did)
    assert repaired == 1

    result = _definition(db_session, entry.id)
    assert 'href="entry://苹果"' in result
    assert f'href="/dict-res/{did}/res/audio/guo.spx"' in result
    assert "/res/entry:/" not in result
    assert "/res/sound:/" not in result


def test_repair_fixes_file_scheme_links(db_session: Session) -> None:
    """汉典、千篇汉语词典、说文解字段注、大辭海、朗文 LDOCE5 等 7 部词典的图片引用。

    实测这类引用约 99 万行，全是 `<img src>`，指向 .mdd 里的图片——「恢复成资源 URL」是
    正确的还原，不是把危险协议变成可执行内容。
    """
    did = _make_dictionary(db_session).id
    entry = _add_entry(
        db_session,
        did,
        "汉",
        f'<img src="/dict-res/{did}/res/file:/down/7/78373w1b6c49.gif">',
    )

    assert count_legacy_links(db_session, did) == (0, 0, 1)
    assert repair_legacy_links(db_session, did) == 1

    result = _definition(db_session, entry.id)
    assert result == f'<img src="/dict-res/{did}/res/down/7/78373w1b6c49.gif">'
    assert "/res/file:/" not in result


def test_repair_result_matches_new_import_output(db_session: Session) -> None:
    """修复后的值必须与新导入代码对同一份原始释义的产出一致。

    这是「修复能否完整还原旧库」的核心保证：两条路径殊途同归。
    """
    did = _make_dictionary(db_session).id
    original = (
        "<style>p{margin:0}</style>"
        '<a href="entry://苹果">苹果</a>'
        '<a href="sound://audio/guo.spx">🔊</a>'
        '<img src="pic/apple.png">'
        '<img src="file:///down/7/x.gif">'
        '<a href="https://example.com">站外</a>'
        '<a href="#top">顶部</a>'
    )
    entry = _add_entry(db_session, did, "混合", _legacy(did, original))

    repair_legacy_links(db_session, did)

    assert _definition(db_session, entry.id) == rewrite_resource_refs(original, did)



def test_repair_is_idempotent(db_session: Session) -> None:
    did = _make_dictionary(db_session).id
    entry = _add_entry(db_session, did, "词", f'<a href="/dict-res/{did}/res/entry:/x">x</a>')

    assert repair_legacy_links(db_session, did) == 1
    fixed = _definition(db_session, entry.id)
    # 再来一次不应改动任何行，也不应把已修好的值改坏
    assert repair_legacy_links(db_session, did) == 0
    assert _definition(db_session, entry.id) == fixed


def test_dry_run_writes_nothing(db_session: Session) -> None:
    did = _make_dictionary(db_session).id
    legacy = f'<a href="/dict-res/{did}/res/entry:/x">x</a>'
    entry = _add_entry(db_session, did, "词", legacy)

    affected = repair_legacy_links(db_session, did, dry_run=True)
    assert affected == 1
    assert _definition(db_session, entry.id) == legacy


def test_repair_leaves_dangerous_urls_untouched(db_session: Session) -> None:
    """javascript: 不是被改写坏的，恢复它等于重新引入可执行内容。

    这里同时钉住一个**刻意的不对称**：没有被改写过的 `file:///etc/passwd` 原文不动。
    它可能指向本机文件、也可能是词典内部资源，从文本上区分不了（要靠文件系统，那是
    `/dict-res` 路由的活儿）；而新导入的词典会把它改写成 `/dict-res/{id}/res/etc/passwd`
    ——一个 404，但原本的 `file://` 在浏览器里同样打不开，两种结果都不会更糟。
    """
    did = _make_dictionary(db_session).id
    definition = (
        '<a href="javascript:alert(1)">x</a>'
        '<a href="file:///etc/passwd">y</a>'
        f'<a href="/dict-res/{did}/res/entry:/ok">z</a>'
    )
    entry = _add_entry(db_session, did, "混合", definition)

    repair_legacy_links(db_session, did)

    result = _definition(db_session, entry.id)
    assert 'href="javascript:alert(1)"' in result
    assert 'href="file:///etc/passwd"' in result
    assert 'href="entry://ok"' in result


def test_repair_respects_batch_boundaries(db_session: Session) -> None:
    """分批时不能漏掉区间边界上的行，也不能越到 MAX(id) 之外。"""
    did = _make_dictionary(db_session).id
    entries = [
        _add_entry(db_session, did, f"w{i}", f'<a href="/dict-res/{did}/res/entry:/w{i}">w</a>')
        for i in range(7)
    ]

    repaired = repair_legacy_links(db_session, did, batch_size=2)
    assert repaired == 7
    for i, entry in enumerate(entries):
        assert _definition(db_session, entry.id) == f'<a href="entry://w{i}">w</a>'


def test_repair_is_scoped_to_one_dictionary(db_session: Session) -> None:
    """另一部词典（id 不同，坏链接前缀也不同）不应被改动。"""
    first = _make_dictionary(db_session, "甲").id
    second = _make_dictionary(db_session, "乙").id
    other_definition = f'<a href="/dict-res/{second}/res/entry:/x">x</a>'
    mine = _add_entry(db_session, first, "词", f'<a href="/dict-res/{first}/res/entry:/x">x</a>')
    other = _add_entry(db_session, second, "词", other_definition)

    assert repair_legacy_links(db_session, first) == 1
    assert _definition(db_session, mine.id) == '<a href="entry://x">x</a>'
    # 乙的坏链接前缀是它自己的 id，修甲时不应被匹配到
    assert _definition(db_session, other.id) == other_definition


def test_repair_ignores_unrelated_dict_res_links(db_session: Session) -> None:
    """指向别的词典资源的正常链接不能被误改。"""
    did = _make_dictionary(db_session).id
    definition = '<img src="/dict-res/999/res/pic/a.png">'
    entry = _add_entry(db_session, did, "词", definition)

    assert repair_legacy_links(db_session, did) == 0
    assert _definition(db_session, entry.id) == definition


def test_count_legacy_links_reports_per_scheme(db_session: Session) -> None:
    did = _make_dictionary(db_session).id
    _add_entry(db_session, did, "a", f'<a href="/dict-res/{did}/res/entry:/a">a</a>')
    _add_entry(
        db_session,
        did,
        "b",
        f'<a href="/dict-res/{did}/res/entry:/b">b</a>'
        f'<a href="/dict-res/{did}/res/sound:/b.spx">🔊</a>'
        f'<img src="/dict-res/{did}/res/file:/img/b.png">',
    )
    _add_entry(db_session, did, "c", "<p>无关</p>")

    assert count_legacy_links(db_session, did) == (2, 1, 1)


def test_repair_on_dictionary_without_entries(db_session: Session) -> None:
    did = _make_dictionary(db_session).id
    assert repair_legacy_links(db_session, did) == 0
    assert count_legacy_links(db_session, did) == (0, 0, 0)


# ---------------------------------------------------------------------------
# 样式标记（`` `编号` ``）的存量展开
# ---------------------------------------------------------------------------

_STYLE_SHEET = {
    "1": ("<b><center><font size=5 color=Green>", "</font></center></b><hr>"),
    "2": ("<br>", ""),
    "7": ("<font color=Red>", "</font>"),
}


def test_expand_stored_styles_rewrites_only_rows_with_markers(db_session: Session) -> None:
    did = _make_dictionary(db_session).id
    marked = _add_entry(db_session, did, "标记", "`1`不`2``7`◆不`2`")
    plain = _add_entry(db_session, did, "普通", "<p>没有标记</p>")

    assert expand_stored_styles(db_session, did, _STYLE_SHEET) == 1

    assert _definition(db_session, marked.id) == (
        "<b><center><font size=5 color=Green>不"
        "</font></center></b><hr>"
        "<br><font color=Red>◆不</font><br>"
    )
    # 不含标记的行不该被碰
    assert _definition(db_session, plain.id) == "<p>没有标记</p>"


def test_expand_stored_styles_is_idempotent(db_session: Session) -> None:
    """展开过之后不再剩已定义的编号，第二次跑改动 0 行——存量修复能安全重复执行。"""
    did = _make_dictionary(db_session).id
    entry = _add_entry(db_session, did, "标记", "`1`不`2`")

    assert expand_stored_styles(db_session, did, _STYLE_SHEET) == 1
    assert expand_stored_styles(db_session, did, _STYLE_SHEET) == 0
    # 内容也不该变
    once = _definition(db_session, entry.id)
    expand_stored_styles(db_session, did, _STYLE_SHEET)
    assert _definition(db_session, entry.id) == once


def test_expand_stored_styles_keeps_undefined_numbers(db_session: Session) -> None:
    """编号不在样式表里时该行原样保留（同库里有词典的正文恰好含反引号数字但没有样式表）。"""
    did = _make_dictionary(db_session).id
    entry = _add_entry(db_session, did, "巧合", "<p>`99`苹果</p>")

    assert expand_stored_styles(db_session, did, _STYLE_SHEET) == 0
    assert _definition(db_session, entry.id) == "<p>`99`苹果</p>"


def test_expand_stored_styles_spans_many_batches(db_session: Session) -> None:
    """分批按主键区间推进，不能漏掉跨批的行。"""
    did = _make_dictionary(db_session).id
    rows = 25
    ids = [_add_entry(db_session, did, f"w{index}", "`7`红`1`").id for index in range(rows)]

    assert expand_stored_styles(db_session, did, _STYLE_SHEET, batch_size=4) == rows
    for entry_id in ids:
        definition = _definition(db_session, entry_id)
        assert definition.startswith("<font color=Red>红")
        assert definition.endswith("</font></center></b><hr>")


def test_expand_stored_styles_on_empty_dictionary(db_session: Session) -> None:
    did = _make_dictionary(db_session).id
    assert expand_stored_styles(db_session, did, _STYLE_SHEET) == 0


def test_dictionaries_using_style_markers_intersects_requested(db_session: Session) -> None:
    a = _make_dictionary(db_session, "有标记").id
    b = _make_dictionary(db_session, "没标记").id
    _add_entry(db_session, a, "x", "`1`x")
    _add_entry(db_session, b, "y", "<p>y</p>")

    assert dictionaries_using_style_markers(db_session, {a, b}) == {a}
    assert dictionaries_using_style_markers(db_session, {b}) == set()
