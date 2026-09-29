"""用户可用词典（管理员配置）与用户 Token（以用户身份调用对外 API）的用例。"""

import uuid

from httpx import AsyncClient

from tests.test_allowed_dictionaries import _create_enabled_dictionary


async def _create_user(client: AsyncClient, admin_headers: dict[str, str]) -> dict:
    username = f"tok{uuid.uuid4().hex[:8]}"
    resp = await client.post("/api/admin/users", json={"username": username}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    login = await client.post(
        "/api/auth/login", json={"username": username, "password": body["temporary_password"]}
    )
    assert login.status_code == 200, login.text
    return {
        **body["user"],
        "headers": {"Authorization": f"Bearer {login.json()['access_token']}"},
    }


async def _admin_user_row(client: AsyncClient, admin_headers: dict[str, str], user: dict) -> dict:
    resp = await client.get(
        "/api/admin/users", params={"search": user["username"]}, headers=admin_headers
    )
    return next(row for row in resp.json()["items"] if row["id"] == user["id"])


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_admin_sets_user_allowed_dictionaries(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    word = f"ua{uuid.uuid4().hex[:6]}"
    dict_a = await _create_enabled_dictionary(
        client, admin_headers, f"用户限定A-{word}", "en", "zh-Hans", [{"word": word}]
    )
    dict_b = await _create_enabled_dictionary(
        client, admin_headers, f"用户限定B-{word}", "en", "zh-Hans", [{"word": word}]
    )
    user = await _create_user(client, admin_headers)
    assert user["allowed_dictionary_ids"] is None

    resp = await client.put(
        f"/api/admin/users/{user['id']}/allowed-dictionaries",
        json={"dictionary_ids": [dict_a, 999999]},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["allowed_dictionary_ids"] == [dict_a]  # 不存在的 id 被过滤

    resp = await client.get("/api/dict/search", params={"word": word}, headers=user["headers"])
    assert {r["dictionary_id"] for r in resp.json()["results"]} == {dict_a}

    resp = await client.put(
        f"/api/admin/users/{user['id']}/allowed-dictionaries",
        json={"dictionary_ids": None},
        headers=admin_headers,
    )
    assert resp.json()["allowed_dictionary_ids"] is None
    resp = await client.get("/api/dict/search", params={"word": word}, headers=user["headers"])
    assert {r["dictionary_id"] for r in resp.json()["results"]} >= {dict_a, dict_b}


async def test_user_token_acts_as_user(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    """用户 Token：可用词典跟随用户、查询进用户历史、生词本是用户自己的。"""
    word = f"ut{uuid.uuid4().hex[:6]}"
    dict_a = await _create_enabled_dictionary(
        client, admin_headers, f"用户令牌A-{word}", "en", "zh-Hans", [{"word": word}]
    )
    await _create_enabled_dictionary(
        client, admin_headers, f"用户令牌B-{word}", "en", "zh-Hans", [{"word": word}]
    )
    user = await _create_user(client, admin_headers)
    await client.put(
        f"/api/admin/users/{user['id']}/allowed-dictionaries",
        json={"dictionary_ids": [dict_a]},
        headers=admin_headers,
    )

    resp = await client.post(f"/api/admin/users/{user['id']}/token", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    token = resp.json()["api_token"]
    assert token and token.startswith("sk-")
    assert (await _admin_user_row(client, admin_headers, user))["api_token"] == token

    resp = await client.get("/api/v1/query", params={"word": word}, headers=_bearer(token))
    assert resp.status_code == 200, resp.text
    assert {r["dictionary_id"] for r in resp.json()["results"]} == {dict_a}

    history = await client.get("/api/dict/history", headers=user["headers"])
    assert word in [item["word"] for item in history.json()["items"]]

    resp = await client.post(
        "/api/v1/vocab", json={"word": word, "dictionary_id": dict_a}, headers=_bearer(token)
    )
    assert resp.status_code == 200, resp.text
    web_vocab = await client.get("/api/vocab", headers=user["headers"])
    assert word in [item["word"] for item in web_vocab.json()["items"]]
    api_vocab = await client.get("/api/v1/vocab", headers=_bearer(token))
    assert word in [item["word"] for item in api_vocab.json()["items"]]

    # Token 管理列表里能看到所属用户，但可用词典不能单独设置
    tokens = (await client.get("/api/admin/tokens", headers=admin_headers)).json()
    row = next(t for t in tokens if t["user_id"] == user["id"])
    assert row["username"] == user["username"]
    resp = await client.put(
        f"/api/admin/tokens/{row['id']}/allowed-dictionaries",
        json={"dictionary_ids": None},
        headers=admin_headers,
    )
    assert resp.status_code == 409


async def test_user_token_regenerate_delete_and_disable(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    user = await _create_user(client, admin_headers)
    first = (
        await client.post(f"/api/admin/users/{user['id']}/token", headers=admin_headers)
    ).json()["api_token"]
    second = (
        await client.post(f"/api/admin/users/{user['id']}/token", headers=admin_headers)
    ).json()["api_token"]
    assert second != first
    assert (await client.get("/api/v1/dictionaries", headers=_bearer(first))).status_code == 401
    assert (await client.get("/api/v1/dictionaries", headers=_bearer(second))).status_code == 200

    # 从 Token 管理页重新生成，用户表里的明文同步更新
    tokens = (await client.get("/api/admin/tokens", headers=admin_headers)).json()
    token_id = next(t["id"] for t in tokens if t["user_id"] == user["id"])
    third = (
        await client.post(f"/api/admin/tokens/{token_id}/regenerate", headers=admin_headers)
    ).json()["token"]
    assert (await _admin_user_row(client, admin_headers, user))["api_token"] == third

    # 用户被禁用：Token 一并失效
    await client.put(f"/api/admin/users/{user['id']}/disable", headers=admin_headers)
    assert (await client.get("/api/v1/dictionaries", headers=_bearer(third))).status_code == 403
    await client.put(f"/api/admin/users/{user['id']}/enable", headers=admin_headers)
    assert (await client.get("/api/v1/dictionaries", headers=_bearer(third))).status_code == 200

    resp = await client.delete(f"/api/admin/users/{user['id']}/token", headers=admin_headers)
    assert resp.status_code == 200 and resp.json()["api_token"] is None
    assert (await client.get("/api/v1/dictionaries", headers=_bearer(third))).status_code == 401
    tokens = (await client.get("/api/admin/tokens", headers=admin_headers)).json()
    assert all(t["user_id"] != user["id"] for t in tokens)
    resp = await client.delete(f"/api/admin/users/{user['id']}/token", headers=admin_headers)
    assert resp.status_code == 404


async def test_plain_token_keeps_its_own_vocab_and_no_plaintext(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """普通 Token 不受影响：不存明文、不关联用户。"""
    resp = await client.post(
        "/api/admin/tokens", json={"name": f"plain-{uuid.uuid4().hex[:6]}"}, headers=admin_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] is None and body["username"] is None

    from app.core.db import SessionLocal
    from app.models.token import ApiToken

    with SessionLocal() as db:
        assert db.get(ApiToken, body["id"]).token_plain is None


async def test_user_self_service_api_token(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """前台用户菜单「Token 管理」：查看、分配、重新分配自己的 Token。"""
    user = await _create_user(client, admin_headers)
    assert (await client.get("/api/auth/api-token")).status_code == 401

    resp = await client.get("/api/auth/api-token", headers=user["headers"])
    assert resp.status_code == 200 and resp.json() == {"api_token": None}

    first = (await client.post("/api/auth/api-token", headers=user["headers"])).json()["api_token"]
    assert first and first.startswith("sk-")
    resp = await client.get("/api/auth/api-token", headers=user["headers"])
    assert resp.json()["api_token"] == first
    assert (await _admin_user_row(client, admin_headers, user))["api_token"] == first
    assert (await client.get("/api/v1/dictionaries", headers=_bearer(first))).status_code == 200

    second = (await client.post("/api/auth/api-token", headers=user["headers"])).json()["api_token"]
    assert second != first
    assert (await client.get("/api/v1/dictionaries", headers=_bearer(first))).status_code == 401
    assert (await client.get("/api/v1/dictionaries", headers=_bearer(second))).status_code == 200


async def test_user_self_selection_stays_within_admin_limit(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """管理员划定上限后，用户在前台「词典选择」里只能在上限内挑，改回「全部」也越不过上限。"""
    word = f"ul{uuid.uuid4().hex[:6]}"
    dicts = [
        await _create_enabled_dictionary(
            client, admin_headers, f"上限{tag}-{word}", "en", "zh-Hans", [{"word": word}]
        )
        for tag in "ABC"
    ]
    dict_a, dict_b, dict_c = dicts
    user = await _create_user(client, admin_headers)
    headers = user["headers"]

    async def searched() -> set[int]:
        resp = await client.get("/api/dict/search", params={"word": word}, headers=headers)
        return {r["dictionary_id"] for r in resp.json()["results"]} & set(dicts)

    async def listed(scope: str) -> set[int]:
        resp = await client.get("/api/dict/dictionaries", params={"scope": scope}, headers=headers)
        return {d["id"] for d in resp.json()} & set(dicts)

    await client.put(
        f"/api/admin/users/{user['id']}/allowed-dictionaries",
        json={"dictionary_ids": [dict_a, dict_b]},
        headers=admin_headers,
    )
    # 用户菜单的弹窗只列上限内的；管理端看到的是上限本身
    assert await listed("all") == {dict_a, dict_b}
    assert await searched() == {dict_a, dict_b}

    resp = await client.put(
        "/api/auth/allowed-dictionaries",
        json={"dictionary_ids": [dict_a, dict_c]},
        headers=headers,
    )
    assert resp.json()["allowed_dictionary_ids"] == [dict_a]  # 上限外的 C 被丢掉
    assert await searched() == {dict_a}
    assert await listed("usable") == {dict_a}
    assert (await _admin_user_row(client, admin_headers, user))["allowed_dictionary_ids"] == [
        dict_a,
        dict_b,
    ]

    await client.put(
        "/api/auth/allowed-dictionaries", json={"dictionary_ids": None}, headers=headers
    )
    assert await searched() == {dict_a, dict_b}

    # 管理员收窄上限后，用户原先的自选落在上限外时退回上限，而不是变成不限制
    await client.put(
        "/api/auth/allowed-dictionaries", json={"dictionary_ids": [dict_a]}, headers=headers
    )
    await client.put(
        f"/api/admin/users/{user['id']}/allowed-dictionaries",
        json={"dictionary_ids": [dict_b]},
        headers=admin_headers,
    )
    assert await searched() == {dict_b}
    resp = await client.get(
        "/api/v1/query",
        params={"word": word},
        headers=_bearer(
            (
                await client.post(f"/api/admin/users/{user['id']}/token", headers=admin_headers)
            ).json()["api_token"]
        ),
    )
    assert {r["dictionary_id"] for r in resp.json()["results"]} & set(dicts) == {dict_b}
