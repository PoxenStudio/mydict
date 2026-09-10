from httpx import AsyncClient


async def test_register_login_change_password(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/auth/register", json={"username": "alice", "password": "alicepass123"}
    )
    assert resp.status_code == 200

    # 用户名重复注册应被拒绝
    resp = await client.post(
        "/api/auth/register", json={"username": "alice", "password": "anotherpass123"}
    )
    assert resp.status_code == 409

    resp = await client.post(
        "/api/auth/login", json={"username": "alice", "password": "alicepass123"}
    )
    assert resp.status_code == 200
    access_token = resp.json()["access_token"]

    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"

    resp = await client.post(
        "/api/auth/change-password",
        json={"old_password": "wrong", "new_password": "newpass1234"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 401

    resp = await client.post(
        "/api/auth/change-password",
        json={"old_password": "alicepass123", "new_password": "newpass1234"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200

    resp = await client.post(
        "/api/auth/login", json={"username": "alice", "password": "newpass1234"}
    )
    assert resp.status_code == 200


async def test_user_token_cannot_access_admin_scope(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/auth/register", json={"username": "bob", "password": "bobpassword123"}
    )
    assert resp.status_code == 200
    resp = await client.post(
        "/api/auth/login", json={"username": "bob", "password": "bobpassword123"}
    )
    access_token = resp.json()["access_token"]

    resp = await client.get("/api/admin/me", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 401


async def test_unauthenticated_requests_rejected(client: AsyncClient) -> None:
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401
    resp = await client.get("/api/admin/me")
    assert resp.status_code == 401
