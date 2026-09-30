"""随机浏览端点的用例：开关门控、范围过滤、加权选择可用性、区间缓存预热与失效。"""

import csv

import pytest
import io

from httpx import AsyncClient

from app.services.settings_service import set_setting
from tests.conftest import import_dictionary


@pytest.fixture(autouse=True)
def _clear_bounds_cache():
    """区间缓存在进程级存活（TTL 1 小时），而各用例的独立数据库会复用词典 id——
    上一个用例预热的区间会污染下一个用例（偶发：随机落点越界）。每个用例前清空。"""
    from app.services import random_entry_service

    random_entry_service.invalidate_bounds()
    yield
    random_entry_service.invalidate_bounds()


def _csv(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["word", "translation"])
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode()


async def test_random_entry_rejected_when_switch_off(client: AsyncClient, db_session) -> None:
    """管理后台默认禁用：接口直接 403，不给用也不消耗限额。"""
    set_setting(db_session, "open_access", "true")
    resp = await client.get("/api/dict/random")
    assert resp.status_code == 403
    assert "未启用" in resp.json()["message"]


async def test_random_switch_off_consume_no_quota(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """开关关着时不该计次：否则管理员一开启，用户当分钟就被自己的限额挡住。"""
    set_setting(db_session, "open_access", "true")
    set_setting(db_session, "anonymous_ip_rate_limit_per_min", "1")
    assert (await client.get("/api/dict/random")).status_code == 403
    assert (await client.get("/api/dict/random")).status_code == 403

    set_setting(db_session, "random_browse_enabled", "true")
    resp = await client.get("/api/dict/random")
    assert resp.status_code in (200, 404), resp.text  # 没被前面的 403 顶成 429


async def test_warm_bounds_fills_cache_for_enabled_dictionaries(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """预热把启用词典的主键区间一次算好，之后首个点击不必等那两秒级扫描。"""
    from app.services import random_entry_service

    random_entry_service.invalidate_bounds()
    d = await import_dictionary(
        client,
        admin_headers,
        data={"name": "预热池", "format": "ecdict", "lang_from": "en", "lang_to": "zh-Hans"},
        files={
            "files": ("warm.csv", _csv([{"word": "warm", "translation": "暖"}]), "text/csv")
        },
    )
    await client.put(f"/api/admin/dictionaries/{d['id']}/enable", headers=admin_headers)

    assert random_entry_service.warm_bounds(db_session) >= 1
    assert d["id"] in random_entry_service._BOUNDS_CACHE


async def test_enabling_switch_in_admin_starts_warming(
    client: AsyncClient, admin_headers: dict[str, str], db_session, monkeypatch
) -> None:
    """从关到开的那一刻就预热（管理员不必等到重启）；本来就开着、或又关掉都不触发。"""
    from app.services import random_entry_service

    set_setting(db_session, "open_access", "true")
    warmed: list[bool] = []
    monkeypatch.setattr(
        random_entry_service,
        "warm_bounds_in_background",
        lambda: warmed.append(True) or True,
    )

    resp = await client.put(
        "/api/admin/settings", json={"random_browse_enabled": True}, headers=admin_headers
    )
    assert resp.status_code == 200
    assert warmed == [True]

    # 已经是开着的：再保存一次不该重复预热
    await client.put(
        "/api/admin/settings", json={"random_browse_enabled": True}, headers=admin_headers
    )
    assert warmed == [True]

    # 关掉：不预热，且接口立刻回到 403
    await client.put(
        "/api/admin/settings", json={"random_browse_enabled": False}, headers=admin_headers
    )
    assert warmed == [True]
    assert (await client.get("/api/dict/random")).status_code == 403


async def test_random_entry_picks_from_requested_pool(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    set_setting(db_session, "open_access", "true")
    set_setting(db_session, "random_browse_enabled", "true")
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
    set_setting(db_session, "random_browse_enabled", "true")
    resp = await client.get("/api/dict/random", params={"dict_ids": "999999"})
    assert resp.status_code == 404


async def test_random_entry_counts_against_rate_limit(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """随机浏览与查询共用按 IP 限额：限额耗尽后返回 429。"""
    set_setting(db_session, "open_access", "true")
    set_setting(db_session, "random_browse_enabled", "true")
    set_setting(db_session, "anonymous_ip_rate_limit_per_min", "1")
    resp = await client.get("/api/dict/random")
    assert resp.status_code in (200, 404)  # 词典池可能为空，但限额已计次
    resp2 = await client.get("/api/dict/random")
    assert resp2.status_code == 429


async def test_random_entry_picks_single_entry_dictionary(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """只有一条词条的词典主键区间 lo == hi，也必须能被随机到。"""
    set_setting(db_session, "open_access", "true")
    set_setting(db_session, "random_browse_enabled", "true")
    d = await import_dictionary(
        client,
        admin_headers,
        data={"name": "随机单条", "format": "ecdict", "lang_from": "en", "lang_to": "zh-Hans"},
        files={"files": ("one.csv", _csv([{"word": "solo", "translation": "独"}]), "text/csv")},
    )
    enable = await client.put(f"/api/admin/dictionaries/{d['id']}/enable", headers=admin_headers)
    assert enable.status_code == 200, enable.text

    resp = await client.get("/api/dict/random", params={"dict_ids": str(d["id"])})
    assert resp.status_code == 200, resp.text
    assert resp.json()["word"] == "solo"


async def test_random_bounds_cache_cleared_when_dictionary_deleted(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """删除词典后主键区间缓存必须失效，不能等 TTL 过期。"""
    from app.services import random_entry_service

    set_setting(db_session, "open_access", "true")
    set_setting(db_session, "random_browse_enabled", "true")
    d = await import_dictionary(
        client,
        admin_headers,
        data={"name": "随机删除", "format": "ecdict", "lang_from": "en", "lang_to": "zh-Hans"},
        files={"files": ("gone.csv", _csv([{"word": "gone", "translation": "去"}]), "text/csv")},
    )
    await client.put(f"/api/admin/dictionaries/{d['id']}/enable", headers=admin_headers)
    resp = await client.get("/api/dict/random", params={"dict_ids": str(d["id"])})
    assert resp.status_code == 200, resp.text
    assert d["id"] in random_entry_service._BOUNDS_CACHE

    resp = await client.delete(f"/api/admin/dictionaries/{d['id']}", headers=admin_headers)
    assert resp.status_code in (200, 204), resp.text
    assert d["id"] not in random_entry_service._BOUNDS_CACHE
