"""词条重定向（MDict 的 `@@@LINK=`）的用例。

词典制作者用 `@@@LINK=目标词条` 表示「本词条与目标词条同义」，拿它做同义词、大小写、简繁
变体，以及日语词典里的「見出し語 → 見出し語【読み】」跳转。实测用户库里这类条目有
10,505,543 条（占 2468 万词条的 42%，moji辞書 一部就 14.5 万），不解析的话用户看到的
就是这一行标记本身。

所有查询都用 `dict=` 限定到本用例造的词典：测试库是整轮共用的，不限定就会撞上别的
用例造的同名词条。
"""

import csv
import io

from httpx import AsyncClient

from app.services.settings_service import set_setting
from tests.conftest import import_dictionary


def _ecdict_csv(rows: list[tuple[str, str]]) -> bytes:
    fieldnames = ["word", "phonetic", "definition", "translation", "exchange"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for word, definition in rows:
        writer.writerow({"word": word, "phonetic": "", "definition": definition, "exchange": ""})
    return buf.getvalue().encode("utf-8")


async def _make_dictionary(
    client: AsyncClient, admin_headers: dict[str, str], name: str, rows: list[tuple[str, str]]
) -> int:
    dictionary = await import_dictionary(
        client,
        admin_headers,
        data={"name": name, "format": "ecdict", "lang_from": "zh", "lang_to": "zh"},
        files={"files": (f"{name}.csv", _ecdict_csv(rows), "text/csv")},
    )
    resp = await client.put(
        f"/api/admin/dictionaries/{dictionary['id']}/enable", headers=admin_headers
    )
    assert resp.status_code == 200
    return dictionary["id"]


async def _search(client: AsyncClient, word: str, dictionary_id: int) -> dict:
    """走对外 API：前台 /dict/search 不带释义（释义另走 /dict/entry），这里要断言释义本身。"""
    resp = await client.get(
        "/api/v1/query",
        params={"word": word, "dict": str(dictionary_id), "full_style": "true"},
    )
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert len(results) == 1, results
    return results[0]


async def test_web_search_omits_definitions(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """前台结果不带释义（释义走 /dict/entry），对外 API 照常带。"""
    dict_id = await _make_dictionary(
        client,
        admin_headers,
        "前台无释义",
        [("中国", "@@@LINK=中国【ちゅうごく①】"), ("中国【ちゅうごく①】", "中华人民共和国。")],
    )
    set_setting(db_session, "open_access", "true")

    resp = await client.get("/api/dict/search", params={"word": "中国", "dict": str(dict_id)})
    assert resp.status_code == 200, resp.text
    (result,) = resp.json()["results"]
    assert "definition" not in result
    assert result["word"] == "中国" and result["id"] > 0

    # 同一个词先走前台再走对外 API：缓存按「带不带释义」分开，对外 API 仍拿到释义
    assert "中华人民共和国" in (await _search(client, "中国", dict_id))["definition"]


async def test_search_follows_link_redirect(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """查「中国」拿到的应该是目标词条的正文，而不是 `@@@LINK=…` 这行标记。"""
    dict_id = await _make_dictionary(
        client,
        admin_headers,
        "跳转词典",
        [
            ("中国", "@@@LINK=中国【ちゅうごく①】"),
            ("中国【ちゅうごく①】", "中国，中华人民共和国。"),
        ],
    )
    set_setting(db_session, "open_access", "true")

    result = await _search(client, "中国", dict_id)
    assert "@@@LINK" not in result["definition"]
    assert "中华人民共和国" in result["definition"]
    # 词头仍是用户查到的那个，不该突然变成目标写法
    assert result["word"] == "中国"


async def test_entry_document_follows_link_redirect(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """词条 HTML 接口同样要跟进重定向——它正是 iframe 里渲染的那份内容。"""
    dict_id = await _make_dictionary(
        client,
        admin_headers,
        "跳转词条",
        [
            ("apple", "@@@LINK=apple（苹果）"),
            ("apple（苹果）", "<p>苹果，一种水果。</p>"),
        ],
    )
    set_setting(db_session, "open_access", "true")

    resp = await client.get(f"/api/dict/entry/{dict_id}", params={"word": "apple"})
    assert resp.status_code == 200, resp.text
    assert "一种水果" in resp.text
    assert "@@@LINK" not in resp.text


async def test_link_redirect_follows_chains(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """多级跳转（A→B→C）要一路跟到底。"""
    dict_id = await _make_dictionary(
        client,
        admin_headers,
        "链式跳转",
        [
            ("链跳甲", "@@@LINK=链跳乙"),
            ("链跳乙", "@@@LINK=链跳丙"),
            ("链跳丙", "最终释义"),
        ],
    )
    set_setting(db_session, "open_access", "true")

    assert "最终释义" in (await _search(client, "链跳甲", dict_id))["definition"]


async def test_link_redirect_survives_cycles(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """互相指向的环不能把查询拖死；跟不下去时就退化成显示那行标记。"""
    dict_id = await _make_dictionary(
        client,
        admin_headers,
        "环形跳转",
        [
            ("环跳甲", "@@@LINK=环跳乙"),
            ("环跳乙", "@@@LINK=环跳甲"),
        ],
    )
    set_setting(db_session, "open_access", "true")

    assert (await _search(client, "环跳甲", dict_id))["definition"]


async def test_link_redirect_falls_back_when_target_missing(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """目标词条缺失时保留原样，比返回空内容好排查。"""
    dict_id = await _make_dictionary(
        client, admin_headers, "断链跳转", [("孤儿词", "@@@LINK=并不存在的词")]
    )
    set_setting(db_session, "open_access", "true")

    assert "@@@LINK" in (await _search(client, "孤儿词", dict_id))["definition"]


async def test_plain_definition_is_untouched(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """不含重定向的释义要原样返回——别把正文里出现的 `@@@LINK` 字样也当成跳转。"""
    definition = "正文里提到 @@@LINK 这个标记，但本条不是重定向。"
    dict_id = await _make_dictionary(
        client, admin_headers, "普通释义", [("普通词", definition)]
    )
    set_setting(db_session, "open_access", "true")

    assert (await _search(client, "普通词", dict_id))["definition"] == definition
