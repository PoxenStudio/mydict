"""前台搜索的「精确未命中 → 前缀兜底」用例。

不少词典的 MDict 词头带注记后缀（Japanese Education Vocabulary 的「あ【亜】」、
搜韵的「中国【ちゅうごく①】」），对它们做精确匹配永远打不中；MDict 客户端与
django-mdict 的搜索都是前缀式的。这里验证：只对精确未命中的词典补前缀结果。
"""

import csv
import io

from httpx import AsyncClient

from app.services.settings_service import set_setting
from tests.conftest import import_dictionary


def _csv_bytes(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["word", "phonetic", "definition", "translation"])
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in writer.fieldnames})
    return buf.getvalue().encode("utf-8")


async def _create_dictionary(
    client: AsyncClient,
    admin_headers: dict[str, str],
    name: str,
    words: list[str],
) -> int:
    dictionary = await import_dictionary(
        client,
        admin_headers,
        data={"name": name, "format": "ecdict", "lang_from": "en", "lang_to": "zh-Hans"},
        files={
            "files": (
                f"{name}.csv",
                _csv_bytes([{"word": w, "translation": "释义"} for w in words]),
                "text/csv",
            )
        },
    )
    resp = await client.put(
        f"/api/admin/dictionaries/{dictionary['id']}/enable", headers=admin_headers
    )
    assert resp.status_code == 200
    return dictionary["id"]


async def _search(client: AsyncClient, word: str, dict_id: int | None = None) -> list[str]:
    params = {"word": word}
    if dict_id is not None:
        params["dict"] = str(dict_id)
    resp = await client.get("/api/dict/search", params=params)
    assert resp.status_code == 200
    return [item["word"] for item in resp.json()["results"]]


async def test_suffixed_headwords_are_found_by_prefix_fallback(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """词头带注记后缀（あ【亜】）的词典，精确匹配打不中时要退回前缀匹配。"""
    dict_id = await _create_dictionary(client, admin_headers, "前缀-注记词头", ["あ【亜】", "ああ"])
    set_setting(db_session, "open_access", "true")

    assert await _search(client, "あ", dict_id) == ["あ【亜】", "ああ"]


async def test_exact_hit_dict_gets_no_prefix_noise(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """有精确命中的词典绝不混入前缀结果：查 apple 只返回 apple，不带 applesauce。"""
    dict_id = await _create_dictionary(
        client, admin_headers, "前缀-精确优先", ["apple", "applesauce"]
    )
    set_setting(db_session, "open_access", "true")

    assert await _search(client, "apple", dict_id) == ["apple"]


async def test_prefix_fallback_is_capped_per_dictionary(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """前缀兜底每部词典最多返回 8 条，避免一个前缀铺出几百条。"""
    words = [f"zzprefix{i:02d}" for i in range(20)]
    dict_id = await _create_dictionary(client, admin_headers, "前缀-限量", words)
    set_setting(db_session, "open_access", "true")

    results = await _search(client, "zzprefix", dict_id)
    assert len(results) == 8
    assert results == sorted(results)
