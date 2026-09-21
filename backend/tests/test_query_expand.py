"""查询扩展（繁简通搜、全角/半角）的用例。

用户的库里既有简体词典也有大量繁体词典（大辭海、漢語大詞典、詩詞鑑賞大全），
输入哪一种写法取决于习惯与输入法——不扩展就总有一半查不到。
"""

import csv
import io

from httpx import AsyncClient

from app.services.query_expand import EXPANSION_VERSION, expand_word
from app.services.settings_service import set_setting
from tests.conftest import import_dictionary


def test_expand_keeps_original_first() -> None:
    variants = expand_word("汉语")
    assert variants[0] == "汉语"
    assert variants == list(dict.fromkeys(variants)), "变体不该重复"


def test_expand_converts_between_simplified_and_traditional() -> None:
    # 简体输入要能覆盖繁体写法
    assert "漢語" in expand_word("汉语")
    assert "電腦" in expand_word("电脑")
    # 繁体输入同理
    assert "汉语" in expand_word("漢語")
    assert "电脑" in expand_word("電腦")


def test_expand_normalizes_fullwidth_ascii() -> None:
    # 输入全角、词典里存半角
    assert "abc" in expand_word("ＡＢＣ")
    # 输入半角、词典里存全角
    assert "ａｐｐｌｅ" in expand_word("apple")


def test_expand_normalizes_halfwidth_katakana() -> None:
    variants = expand_word("ｱｲｳ")
    assert "アイウ" in variants


def test_expand_is_case_insensitive() -> None:
    assert expand_word("Apple")[0] == "apple"


def test_expand_does_not_mangle_plain_text() -> None:
    """扩展只增不减：原词一定在，且不该凭空产出无关词。"""
    for word in ("apple", "苹果", "漢語", "ｱｲｳ"):
        variants = expand_word(word)
        assert variants[0] == word.strip().lower()
        assert len(variants) <= 16


def test_expansion_version_is_exposed_for_cache_keying() -> None:
    """缓存 key 要带上规则版本，否则改了扩展规则后旧结果会在 TTL 内继续被命中。"""
    assert isinstance(EXPANSION_VERSION, int) and EXPANSION_VERSION >= 1


def _ecdict_csv(words: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["word", "translation"])
    writer.writeheader()
    for word in words:
        writer.writerow({"word": word, "translation": "释义内容"})
    return buf.getvalue().encode("utf-8")


async def _make_dict(
    client: AsyncClient, admin_headers: dict[str, str], name: str, lang_from: str, words: list[str]
) -> int:
    dictionary = await import_dictionary(
        client,
        admin_headers,
        data={"name": name, "format": "ecdict", "lang_from": lang_from, "lang_to": "zh-Hans"},
        files={"files": (f"{name}.csv", _ecdict_csv(words), "text/csv")},
    )
    resp = await client.put(
        f"/api/admin/dictionaries/{dictionary['id']}/enable", headers=admin_headers
    )
    assert resp.status_code == 200
    return dictionary["id"]


async def test_simplified_query_hits_traditional_only_dictionary(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """只收繁体词头的词典，用简体输入也要能查到。"""
    dict_id = await _make_dict(client, admin_headers, "繁体词典甲", "zh-Hant", ["漢語大詞典"])
    set_setting(db_session, "open_access", "true")

    resp = await client.get("/api/dict/search", params={"word": "汉语大词典"})
    assert resp.status_code == 200, resp.text
    hits = [item for item in resp.json()["results"] if item["dictionary_id"] == dict_id]
    assert hits, resp.json()
    # 返回的是词典里实际收的词头，前端据此展示
    assert hits[0]["word"] == "漢語大詞典"


async def test_traditional_query_hits_simplified_only_dictionary(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    dict_id = await _make_dict(client, admin_headers, "简体词典乙", "zh-Hans", ["汉语大词典"])
    set_setting(db_session, "open_access", "true")

    resp = await client.get("/api/dict/search", params={"word": "漢語大詞典"})
    assert resp.status_code == 200, resp.text
    hits = [item for item in resp.json()["results"] if item["dictionary_id"] == dict_id]
    assert hits, resp.json()


async def test_expansion_does_not_disable_language_routing(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """扩展只增召回，不该把无关语言的词典也拉进来。"""
    zh_id = await _make_dict(client, admin_headers, "繁体词典丙", "zh-Hant", ["漢語丙"])
    en_id = await _make_dict(client, admin_headers, "英文词典丙", "en", ["hanyubing"])
    set_setting(db_session, "open_access", "true")

    resp = await client.get("/api/dict/search", params={"word": "汉语丙"})
    ids = {item["dictionary_id"] for item in resp.json()["results"]}
    assert zh_id in ids
    assert en_id not in ids
