import csv
import io
import uuid

from httpx import AsyncClient

from app.core import rate_limiter
from app.core.security import hash_api_token
from app.models.token import ApiToken
from app.services.settings_service import set_setting


def _ecdict_csv_bytes(rows: list[dict[str, str]]) -> bytes:
    fieldnames = [
        "word",
        "phonetic",
        "definition",
        "translation",
        "pos",
        "collins",
        "oxford",
        "tag",
        "bnc",
        "frq",
        "exchange",
        "detail",
        "audio",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue().encode("utf-8")


async def _create_enabled_dictionary(
    client: AsyncClient,
    admin_headers: dict[str, str],
    name: str,
    lang_from: str,
    lang_to: str,
    rows: list[dict[str, str]],
) -> int:
    resp = await client.post(
        "/api/admin/dictionaries",
        headers=admin_headers,
        data={"name": name, "format": "ecdict", "lang_from": lang_from, "lang_to": lang_to},
        files={"files": (f"{name}.csv", _ecdict_csv_bytes(rows), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    dict_id = resp.json()["id"]
    resp = await client.put(f"/api/admin/dictionaries/{dict_id}/enable", headers=admin_headers)
    assert resp.status_code == 200
    return dict_id


def _make_api_token(db_session, *, daily_limit: int | None = None) -> tuple[str, ApiToken]:
    raw = f"test-raw-token-{uuid.uuid4().hex}"
    token = ApiToken(
        name="test token",
        token_hash=hash_api_token(raw),
        token_prefix=raw[:8],
        daily_limit=daily_limit,
        status="active",
    )
    db_session.add(token)
    db_session.commit()
    db_session.refresh(token)
    return raw, token


async def test_query_requires_token_unless_open_access(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    set_setting(db_session, "open_access", "false")
    await _create_enabled_dictionary(
        client,
        admin_headers,
        "EN-ZH-A",
        "en",
        "zh",
        [{"word": "hello", "translation": "你好", "phonetic": "helo"}],
    )

    resp = await client.get("/api/v1/query", params={"word": "hello"})
    assert resp.status_code == 401

    set_setting(db_session, "open_access", "true")
    resp = await client.get("/api/v1/query", params={"word": "hello"})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["word"] == "hello"
    assert "你好" in results[0]["definition"]


async def test_query_with_token_and_disabled_token(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    set_setting(db_session, "open_access", "false")
    await _create_enabled_dictionary(
        client,
        admin_headers,
        "EN-ZH-B",
        "en",
        "zh",
        [{"word": "world", "translation": "世界"}],
    )
    raw, token = _make_api_token(db_session)

    resp = await client.get(
        "/api/v1/query",
        params={"word": "world"},
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert resp.status_code == 200
    assert resp.json()["results"][0]["word"] == "world"

    resp = await client.get(
        "/api/v1/query", params={"word": "world"}, headers={"Authorization": "Bearer garbage"}
    )
    assert resp.status_code == 401

    token.status = "disabled"
    db_session.commit()
    resp = await client.get(
        "/api/v1/query",
        params={"word": "world"},
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert resp.status_code == 403


async def test_query_not_found_returns_empty_list(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    set_setting(db_session, "open_access", "true")
    resp = await client.get("/api/v1/query", params={"word": "zzzznotexist"})
    assert resp.status_code == 200
    assert resp.json() == {"results": []}


async def test_suggest_and_list_dictionaries(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    set_setting(db_session, "open_access", "true")
    await _create_enabled_dictionary(
        client,
        admin_headers,
        "EN-ZH-C",
        "en",
        "zh",
        [
            {"word": "cat", "translation": "猫"},
            {"word": "car", "translation": "汽车"},
            {"word": "card", "translation": "卡片"},
        ],
    )
    resp = await client.get("/api/v1/suggest", params={"prefix": "ca", "limit": 10})
    assert resp.status_code == 200
    words = set(resp.json()["words"])
    assert {"cat", "car", "card"} <= words

    resp = await client.get("/api/v1/dictionaries")
    assert resp.status_code == 200
    names = {d["name"] for d in resp.json()}
    assert "EN-ZH-C" in names


async def test_token_daily_rate_limit(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    set_setting(db_session, "open_access", "false")
    await _create_enabled_dictionary(
        client,
        admin_headers,
        "EN-ZH-D",
        "en",
        "zh",
        [{"word": "limited", "translation": "受限"}],
    )
    raw, _token = _make_api_token(db_session, daily_limit=1)
    headers = {"Authorization": f"Bearer {raw}"}

    resp1 = await client.get("/api/v1/query", params={"word": "limited"}, headers=headers)
    assert resp1.status_code == 200

    resp2 = await client.get("/api/v1/query", params={"word": "limited"}, headers=headers)
    assert resp2.status_code == 429
    assert "Retry-After" in resp2.headers


async def test_anonymous_ip_rate_limit(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    rate_limiter.reset()  # 避免同一分钟内其它用例已对同一测试 IP 计数，干扰本用例的边界断言
    set_setting(db_session, "open_access", "true")
    set_setting(db_session, "anonymous_ip_rate_limit_per_min", "1")
    await _create_enabled_dictionary(
        client,
        admin_headers,
        "EN-ZH-E",
        "en",
        "zh",
        [{"word": "anon", "translation": "匿名"}],
    )

    resp1 = await client.get("/api/v1/query", params={"word": "anon"})
    assert resp1.status_code == 200
    resp2 = await client.get("/api/v1/query", params={"word": "anon"})
    assert resp2.status_code == 429
    assert "Retry-After" in resp2.headers

    set_setting(db_session, "anonymous_ip_rate_limit_per_min", "60")


async def test_token_vocab_lifecycle_and_snapshot_matches_query(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    set_setting(db_session, "open_access", "true")
    await _create_enabled_dictionary(
        client,
        admin_headers,
        "EN-ZH-F",
        "en",
        "zh",
        [{"word": "snapshot", "translation": "快照", "phonetic": "snap"}],
    )
    raw, _token = _make_api_token(db_session)
    headers = {"Authorization": f"Bearer {raw}"}

    # 收藏接口始终要求 Token，即使 open_access=true 也不允许匿名收藏
    resp = await client.post("/api/v1/vocab", json={"word": "snapshot"})
    assert resp.status_code == 401

    query_resp = await client.get("/api/v1/query", params={"word": "snapshot"})
    query_definition = query_resp.json()["results"][0]["definition"]

    resp = await client.post("/api/v1/vocab", json={"word": "snapshot"}, headers=headers)
    assert resp.status_code == 200, resp.text
    item = resp.json()
    assert item["word"] == "snapshot"
    assert item["definition"] == query_definition

    # 重复收藏应被拒绝
    resp = await client.post("/api/v1/vocab", json={"word": "snapshot"}, headers=headers)
    assert resp.status_code == 409

    # 收藏不存在的单词
    resp = await client.post("/api/v1/vocab", json={"word": "nosuchword"}, headers=headers)
    assert resp.status_code == 404

    resp = await client.get("/api/v1/vocab", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["word"] == "snapshot"

    item_id = item["id"]
    resp = await client.delete(f"/api/v1/vocab/{item_id}", headers=headers)
    assert resp.status_code == 200

    resp = await client.get("/api/v1/vocab", headers=headers)
    assert resp.json()["total"] == 0


async def test_web_dict_search_and_user_vocab(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    set_setting(db_session, "open_access", "false")
    await _create_enabled_dictionary(
        client,
        admin_headers,
        "EN-ZH-G",
        "en",
        "zh",
        [{"word": "webword", "translation": "网页词"}],
    )

    resp = await client.get("/api/dict/search", params={"word": "webword"})
    assert resp.status_code == 401

    set_setting(db_session, "open_access", "true")
    resp = await client.get("/api/dict/search", params={"word": "webword"})
    assert resp.status_code == 200
    assert resp.json()["results"][0]["word"] == "webword"

    await client.post(
        "/api/auth/register", json={"username": "vocabuser", "password": "vocabpass123"}
    )
    login_resp = await client.post(
        "/api/auth/login", json={"username": "vocabuser", "password": "vocabpass123"}
    )
    user_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    resp = await client.post("/api/vocab", json={"word": "webword"}, headers=user_headers)
    assert resp.status_code == 200, resp.text
    item_id = resp.json()["id"]

    resp = await client.get("/api/vocab", headers=user_headers)
    assert resp.json()["total"] == 1

    resp = await client.delete(f"/api/vocab/{item_id}", headers=user_headers)
    assert resp.status_code == 200

    # 未登录访问用户生词本应始终 401，即使 open_access=true
    resp = await client.get("/api/vocab")
    assert resp.status_code == 401


async def test_public_settings_endpoint(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    set_setting(db_session, "open_access", "false")
    set_setting(db_session, "site_name", "测试词典站")
    resp = await client.get("/api/public/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["open_access"] is False
    assert body["site_name"] == "测试词典站"
    # 不含限流阈值等敏感配置
    assert "token_default_daily_limit" not in body

    set_setting(db_session, "site_name", "MyDict")
