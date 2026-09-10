from httpx import AsyncClient


async def test_bootstrap_and_login_flow(client: AsyncClient) -> None:
    resp = await client.get("/api/admin/bootstrap-status")
    assert resp.json() == {"initialized": False}

    resp = await client.post(
        "/api/admin/setup", json={"username": "admin", "password": "adminpass123"}
    )
    assert resp.status_code == 200
    access_token = resp.json()["access_token"]

    resp = await client.get("/api/admin/bootstrap-status")
    assert resp.json() == {"initialized": True}

    # 重复初始化应被拒绝
    resp = await client.post(
        "/api/admin/setup", json={"username": "admin2", "password": "whatever123"}
    )
    assert resp.status_code == 409

    resp = await client.get("/api/admin/me", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"

    resp = await client.post(
        "/api/admin/login", json={"username": "admin", "password": "wrongpass"}
    )
    assert resp.status_code == 401


async def test_admin_token_cannot_access_user_scope(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/admin/login", json={"username": "admin", "password": "adminpass123"}
    )
    access_token = resp.json()["access_token"]

    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 401
