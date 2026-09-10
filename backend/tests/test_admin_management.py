from datetime import date

from httpx import AsyncClient

from app.models.audit import AuditLog
from app.services.settings_service import set_setting
from app.tasks.stats_aggregation import aggregate_date


async def test_token_lifecycle(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    resp = await client.post(
        "/api/admin/tokens",
        json={"name": "第三方插件", "daily_limit": 500},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    created = resp.json()
    assert created["token"].startswith("sk-")
    assert created["token_prefix"] == created["token"][:9] + "****"
    assert created["daily_limit"] == 500
    assert created["status"] == "active"
    token_id = created["id"]

    resp = await client.get("/api/admin/tokens", headers=admin_headers)
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()}
    assert "第三方插件" in names
    # 明文 Token 不应出现在列表接口
    assert all("token" not in t for t in resp.json())

    resp = await client.put(f"/api/admin/tokens/{token_id}/disable", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"

    resp = await client.put(f"/api/admin/tokens/{token_id}/enable", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    resp = await client.get(f"/api/admin/tokens/{token_id}/vocab-count", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == {"count": 0}

    resp = await client.post(f"/api/admin/tokens/{token_id}/regenerate", headers=admin_headers)
    assert resp.status_code == 200
    regenerated = resp.json()
    assert regenerated["token"] != created["token"]
    assert regenerated["id"] == token_id

    # 审计日志应记录创建/禁用/启用/重新生成
    db = _fresh_session()
    try:
        actions = {
            a.action for a in db.query(AuditLog).filter(AuditLog.target == str(token_id)).all()
        }
        assert {"token.create", "token.disabled", "token.active", "token.regenerate"} <= actions
    finally:
        db.close()


async def test_token_not_found(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    resp = await client.put("/api/admin/tokens/999999/disable", headers=admin_headers)
    assert resp.status_code == 404


async def test_admin_create_user(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    resp = await client.post(
        "/api/admin/users",
        json={"username": "createduser", "email": "created@example.com"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["username"] == "createduser"
    assert body["user"]["email"] == "created@example.com"
    assert body["user"]["status"] == "active"
    temp_password = body["temporary_password"]
    assert len(temp_password) >= 8

    # 临时密码应能直接登录
    resp = await client.post(
        "/api/auth/login", json={"username": "createduser", "password": temp_password}
    )
    assert resp.status_code == 200

    # 用户名重复应拒绝
    resp = await client.post(
        "/api/admin/users", json={"username": "createduser"}, headers=admin_headers
    )
    assert resp.status_code == 409


async def test_user_management_lifecycle(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await client.post(
        "/api/auth/register", json={"username": "manageduser", "password": "managedpass123"}
    )
    resp = await client.get(
        "/api/admin/users", params={"search": "manageduser"}, headers=admin_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    user_row = body["items"][0]
    assert user_row["username"] == "manageduser"
    user_id = user_row["id"]

    resp = await client.get(f"/api/admin/users/{user_id}", headers=admin_headers)
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["user"]["username"] == "manageduser"
    assert detail["vocab_items"] == []
    assert detail["recent_queries"] == []

    resp = await client.put(f"/api/admin/users/{user_id}/disable", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"

    # 被禁用用户登录应失败
    resp = await client.post(
        "/api/auth/login", json={"username": "manageduser", "password": "managedpass123"}
    )
    assert resp.status_code == 403

    resp = await client.put(f"/api/admin/users/{user_id}/enable", headers=admin_headers)
    assert resp.status_code == 200

    resp = await client.post(f"/api/admin/users/{user_id}/reset-password", headers=admin_headers)
    assert resp.status_code == 200
    temp_password = resp.json()["temporary_password"]
    assert len(temp_password) >= 8

    resp = await client.post(
        "/api/auth/login", json={"username": "manageduser", "password": temp_password}
    )
    assert resp.status_code == 200


async def test_settings_get_and_partial_update(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.get("/api/admin/settings", headers=admin_headers)
    assert resp.status_code == 200
    original = resp.json()
    assert original["site_name"] == "MyDict"
    assert original["vocab_max_items_per_owner"] is None
    assert original["search_hint_text"] == "小搜一下, 大进一步"

    resp = await client.put(
        "/api/admin/settings", json={"site_name": "我的词典"}, headers=admin_headers
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["site_name"] == "我的词典"
    # 未传的字段不应被覆盖
    assert updated["open_access"] == original["open_access"]
    assert updated["token_default_daily_limit"] == original["token_default_daily_limit"]

    resp = await client.put(
        "/api/admin/settings", json={"vocab_max_items_per_owner": 50}, headers=admin_headers
    )
    assert resp.json()["vocab_max_items_per_owner"] == 50

    # 显式传 null 应能清空回「不限」
    resp = await client.put(
        "/api/admin/settings", json={"vocab_max_items_per_owner": None}, headers=admin_headers
    )
    assert resp.json()["vocab_max_items_per_owner"] is None

    resp = await client.put(
        "/api/admin/settings", json={"site_name": "MyDict"}, headers=admin_headers
    )
    assert resp.json()["site_name"] == "MyDict"

    resp = await client.put(
        "/api/admin/settings", json={"search_hint_text": "欢迎回来"}, headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["search_hint_text"] == "欢迎回来"

    resp = await client.get("/api/public/settings")
    assert resp.json()["search_hint_text"] == "欢迎回来"

    # 超过 100 字上限拒绝
    resp = await client.put(
        "/api/admin/settings", json={"search_hint_text": "长" * 101}, headers=admin_headers
    )
    assert resp.status_code == 422

    resp = await client.put(
        "/api/admin/settings",
        json={"search_hint_text": "小搜一下, 大进一步"},
        headers=admin_headers,
    )
    assert resp.json()["search_hint_text"] == "小搜一下, 大进一步"


async def test_stats_overview_top_words_and_csv_export(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    import csv
    import io

    set_setting(db_session, "open_access", "true")
    resp = await client.post(
        "/api/admin/dictionaries",
        headers=admin_headers,
        data={"name": "STATS-DICT", "format": "ecdict", "lang_from": "en", "lang_to": "zh"},
        files={
            "files": (
                "stats.csv",
                (
                    "word,phonetic,definition,translation,pos,collins,oxford,tag,bnc,frq,"
                    "exchange,detail,audio\nstatword,,,统计词,,,,,,,,,\n"
                ).encode("utf-8"),
                "text/csv",
            )
        },
    )
    dict_id = resp.json()["id"]
    await client.put(f"/api/admin/dictionaries/{dict_id}/enable", headers=admin_headers)

    for _ in range(3):
        await client.get("/api/v1/query", params={"word": "statword"})

    resp = await client.get("/api/admin/stats/overview", headers=admin_headers)
    assert resp.status_code == 200
    overview = resp.json()
    # 直接数 query_logs，无需等定时聚合任务跑过也应立即反映刚才的 3 次查询
    assert overview["today_query_count"] >= 3
    assert overview["dictionary_count"] >= 1

    resp = await client.get(
        "/api/admin/stats/top-words", params={"limit": 5}, headers=admin_headers
    )
    assert resp.status_code == 200
    words = {row["word"] for row in resp.json()}
    assert "statword" in words

    resp = await client.get(
        "/api/admin/stats", params={"dimension": "source"}, headers=admin_headers
    )
    assert resp.status_code == 200
    sources = {row["label"] for row in resp.json()}
    assert "api" in sources

    resp = await client.get(
        "/api/admin/stats",
        params={"dimension": "source", "export": "csv"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert any(r["label"] == "api" for r in rows)

    resp = await client.get(
        "/api/admin/stats", params={"dimension": "notadimension"}, headers=admin_headers
    )
    assert resp.status_code == 422


async def test_stats_aggregation_populates_user_and_anonymous_rows(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    from app.models.query import QueryStatsDaily

    set_setting(db_session, "open_access", "true")
    resp = await client.post(
        "/api/admin/dictionaries",
        headers=admin_headers,
        data={"name": "AGG-DICT", "format": "ecdict", "lang_from": "en", "lang_to": "zh"},
        files={
            "files": (
                "agg.csv",
                (
                    "word,phonetic,definition,translation,pos,collins,oxford,tag,bnc,frq,"
                    "exchange,detail,audio\naggword,,,聚合词,,,,,,,,,\n"
                ).encode("utf-8"),
                "text/csv",
            )
        },
    )
    dict_id = resp.json()["id"]
    await client.put(f"/api/admin/dictionaries/{dict_id}/enable", headers=admin_headers)

    await client.post("/api/auth/register", json={"username": "agguser", "password": "aggpass123"})
    login = await client.post(
        "/api/auth/login", json={"username": "agguser", "password": "aggpass123"}
    )
    user_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    await client.get("/api/dict/search", params={"word": "aggword"}, headers=user_headers)
    await client.get("/api/dict/search", params={"word": "aggword"})  # 匿名

    today = date.today().isoformat()
    aggregate_date(today)

    me = await client.get("/api/auth/me", headers=user_headers)
    user_id = me.json()["id"]

    user_row = (
        db_session.query(QueryStatsDaily)
        .filter(QueryStatsDaily.stat_date == today, QueryStatsDaily.user_id == user_id)
        .first()
    )
    assert user_row is not None
    assert user_row.query_count >= 1

    anon_row = (
        db_session.query(QueryStatsDaily)
        .filter(
            QueryStatsDaily.stat_date == today,
            QueryStatsDaily.token_id.is_(None),
            QueryStatsDaily.user_id.is_(None),
        )
        .first()
    )
    assert anon_row is not None
    assert anon_row.query_count >= 1


def _fresh_session():
    from app.core.db import SessionLocal

    return SessionLocal()
