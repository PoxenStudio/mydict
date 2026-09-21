"""一次性修复命令的用例。

修复代码修好之后，正常的导入路径已经不会再产出坏链接了，所以这里**手工构造遗留行**
（形如 /dict-res/{id}/res/entry:/... 与 /dict-res/{id}/res/sound:/...），
模拟修复前入库的数据。
"""

from sqlalchemy.orm import Session

from app.models.dictionary import DictEntry, Dictionary
from app.services.definition_repair import count_legacy_links, repair_legacy_links
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
    """javascript: / file: 不是被改写坏的，恢复它们等于重新引入可执行内容。"""
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
        f'<a href="/dict-res/{did}/res/sound:/b.spx">🔊</a>',
    )
    _add_entry(db_session, did, "c", "<p>无关</p>")

    assert count_legacy_links(db_session, did) == (2, 1)


def test_repair_on_dictionary_without_entries(db_session: Session) -> None:
    did = _make_dictionary(db_session).id
    assert repair_legacy_links(db_session, did) == 0
    assert count_legacy_links(db_session, did) == (0, 0)
