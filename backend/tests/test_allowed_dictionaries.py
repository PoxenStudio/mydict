import csv
import io
import uuid

from httpx import AsyncClient

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


def _make_api_token(db_session) -> tuple[str, ApiToken]:
    raw = f"test-raw-token-{uuid.uuid4().hex}"
    token = ApiToken(
        name="allowed-dict test token",
        token_hash=hash_api_token(raw),
        token_prefix=raw[:8],
        status="active",
    )
    db_session.add(token)
    db_session.commit()
    db_session.refresh(token)
    return raw, token


async def test_token_allowed_dictionaries_restricts_auto_and_explicit_query(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    dict_a = await _create_enabled_dictionary(
        client, admin_headers, "限定A", "en", "zh-Hans", [{"word": "shared", "translation": "A"}]
    )
    dict_b = await _create_enabled_dictionary(
        client, admin_headers, "限定B", "en", "zh-Hans", [{"word": "shared", "translation": "B"}]
    )
    raw, token = _make_api_token(db_session)
    headers = {"Authorization": f"Bearer {raw}"}

    # 未设置限制时，两部词典都应该命中
    resp = await client.get("/api/v1/query", params={"word": "shared"}, headers=headers)
    assert {r["dictionary_id"] for r in resp.json()["results"]} == {dict_a, dict_b}

    resp = await client.put(
        f"/api/admin/tokens/{token.id}/allowed-dictionaries",
        headers=admin_headers,
        json={"dictionary_ids": [dict_a]},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed_dictionary_ids"] == [dict_a]

    # 自动路由：只应该命中限定内的 A，不该出现 B
    resp = await client.get("/api/v1/query", params={"word": "shared"}, headers=headers)
    assert resp.status_code == 200
    ids = {r["dictionary_id"] for r in resp.json()["results"]}
    assert ids == {dict_a}

    # 显式指定 dict=B 也不能绕过限制，应该查不到
    resp = await client.get(
        "/api/v1/query", params={"word": "shared", "dict": str(dict_b)}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["results"] == []

    # /api/v1/dictionaries 列表也应该跟着收窄
    resp = await client.get("/api/v1/dictionaries", headers=headers)
    assert {d["id"] for d in resp.json()} == {dict_a}


async def test_admin_set_allowed_dictionaries_drops_stale_ids(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    dict_a = await _create_enabled_dictionary(
        client, admin_headers, "存在的词典", "en", "zh-Hans", [{"word": "x", "translation": "x"}]
    )
    raw, token = _make_api_token(db_session)

    resp = await client.put(
        f"/api/admin/tokens/{token.id}/allowed-dictionaries",
        headers=admin_headers,
        json={"dictionary_ids": [dict_a, 999999]},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed_dictionary_ids"] == [dict_a]

    # 传全是不存在的 id，应该整体退化成不限制（None），而不是永久查不到任何词
    resp = await client.put(
        f"/api/admin/tokens/{token.id}/allowed-dictionaries",
        headers=admin_headers,
        json={"dictionary_ids": [999999]},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed_dictionary_ids"] is None


async def test_query_from_to_params_select_specific_dictionary(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    set_setting(db_session, "open_access", "true")
    hans = await _create_enabled_dictionary(
        client, admin_headers, "简体测试", "zh-Hans", "en", [{"word": "国", "translation": "简"}]
    )
    hant = await _create_enabled_dictionary(
        client, admin_headers, "繁體测试", "zh-Hant", "en", [{"word": "国", "translation": "繁"}]
    )

    resp = await client.get("/api/v1/query", params={"word": "国", "from": "zh-Hant"})
    assert resp.status_code == 200
    ids = {r["dictionary_id"] for r in resp.json()["results"]}
    assert ids == {hant}
    assert hans not in ids


async def test_user_self_service_allowed_dictionaries(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    dict_a = await _create_enabled_dictionary(
        client, admin_headers, "用户限定A", "en", "zh-Hans", [{"word": "uword", "translation": "A"}]
    )
    dict_b = await _create_enabled_dictionary(
        client, admin_headers, "用户限定B", "en", "zh-Hans", [{"word": "uword", "translation": "B"}]
    )

    await client.post(
        "/api/auth/register", json={"username": "dictuser", "password": "dictpass123"}
    )
    login_resp = await client.post(
        "/api/auth/login", json={"username": "dictuser", "password": "dictpass123"}
    )
    user_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    resp = await client.get("/api/auth/me", headers=user_headers)
    assert resp.json()["allowed_dictionary_ids"] is None

    resp = await client.put(
        "/api/auth/allowed-dictionaries",
        headers=user_headers,
        json={"dictionary_ids": [dict_a]},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed_dictionary_ids"] == [dict_a]

    resp = await client.get("/api/dict/search", params={"word": "uword"}, headers=user_headers)
    ids = {r["dictionary_id"] for r in resp.json()["results"]}
    assert ids == {dict_a}

    # 「词典选择」弹窗用来展示可选项的接口不应该被用户自己已设的限制过滤掉
    resp = await client.get("/api/dict/dictionaries")
    assert {d["id"] for d in resp.json()} >= {dict_a, dict_b}

    # 清空限制恢复成不限制
    resp = await client.put(
        "/api/auth/allowed-dictionaries", headers=user_headers, json={"dictionary_ids": None}
    )
    assert resp.json()["allowed_dictionary_ids"] is None
    resp = await client.get("/api/dict/search", params={"word": "uword"}, headers=user_headers)
    ids = {r["dictionary_id"] for r in resp.json()["results"]}
    assert ids == {dict_a, dict_b}
