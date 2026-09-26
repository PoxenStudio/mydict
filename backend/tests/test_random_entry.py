"""随机浏览端点的用例：范围过滤、加权选择可用性、开放访问门控。"""

import csv
import io

from httpx import AsyncClient

from app.services.settings_service import set_setting
from tests.conftest import import_dictionary


def _csv(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["word", "translation"])
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode()


async def test_random_entry_picks_from_requested_pool(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    set_setting(db_session, "open_access", "true")
    d = await import_dictionary(
        client,
        admin_headers,
        data={"name": "随机池", "format": "ecdict", "lang_from": "en", "lang_to": "zh-Hans"},
        files={
            "files": (
                "pool.csv",
                _csv(
                    [
                        {"word": "alpha", "translation": "甲"},
                        {"word": "beta", "translation": "乙"},
                        {"word": "gamma", "translation": "丙"},
                    ]
                ),
                "text/csv",
            )
        },
    )
    enable = await client.put(f"/api/admin/dictionaries/{d['id']}/enable", headers=admin_headers)
    assert enable.status_code == 200, enable.text

    seen_words = set()
    for _ in range(12):
        resp = await client.get("/api/dict/random", params={"dict_ids": str(d["id"])})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["dictionary_id"] == d["id"]
        assert data["dictionary_name"] == "随机池"
        assert data["entry_id"] > 0
        seen_words.add(data["word"])
    # 三条词条都在池里，多次随机应该能覆盖到（12 次全落同一条的概率可忽略）
    assert seen_words == {"alpha", "beta", "gamma"}


async def test_random_entry_respects_unknown_dict_ids(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    set_setting(db_session, "open_access", "true")
    resp = await client.get("/api/dict/random", params={"dict_ids": "999999"})
    assert resp.status_code == 404


async def test_random_entry_counts_against_rate_limit(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """随机浏览与查询共用按 IP 限额：限额耗尽后返回 429。"""
    set_setting(db_session, "open_access", "true")
    set_setting(db_session, "anonymous_ip_rate_limit_per_min", "1")
    resp = await client.get("/api/dict/random")
    assert resp.status_code in (200, 404)  # 词典池可能为空，但限额已计次
    resp2 = await client.get("/api/dict/random")
    assert resp2.status_code == 429
