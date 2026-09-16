import asyncio
import os
import tempfile
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient

_tmp_dir = tempfile.mkdtemp(prefix="mydict-test-")
os.environ["DATABASE_PATH"] = os.path.join(_tmp_dir, "db", "mydict.sqlite3")
os.environ["CONFIG_STORAGE_PATH"] = os.path.join(_tmp_dir, "config")
os.environ["DICTS_INBOX_PATH"] = os.path.join(_tmp_dir, "dicts")
os.environ["DICTIONARY_STORAGE_PATH"] = os.path.join(_tmp_dir, "dictionaries")
os.environ["LOG_DIR"] = os.path.join(_tmp_dir, "logs")
# 定时聚合任务在测试里关闭：避免后台线程并发写 query_stats_daily 与断言竞争。
os.environ["ENABLE_SCHEDULER"] = "false"

# 导入 app 会触发 ensure_data_dirs() + run_migrations()，
# 建表与 system_settings 默认值播种均由 Alembic migration 完成，无需在测试里重复处理。
from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "adminpass123"


@pytest.fixture
def db_session() -> Iterator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def wait_for_task(
    client: AsyncClient, headers: dict[str, str], task_id: int, timeout: float = 5.0
) -> dict:
    """词典导入等接口不再同步跑完才返回，而是立即给出 task_id，真正的处理在后台线程里
    跑；测试用例通过轮询 GET /admin/tasks/{task_id} 等到终态（success/error），避免每个
    用例重复写轮询循环。"""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while True:
        resp = await client.get(f"/api/admin/tasks/{task_id}", headers=headers)
        body = resp.json()
        if body["status"] != "running":
            return body
        if loop.time() > deadline:
            raise AssertionError(f"任务 {task_id} 轮询超时：{body}")
        await asyncio.sleep(0.02)


async def import_dictionary(client: AsyncClient, headers: dict[str, str], **kwargs) -> dict:
    """POST /admin/dictionaries（浏览器上传）并等导入任务跑完，返回完整的词典对象。
    kwargs 透传给 client.post（如 data=..., files=...）。旧版接口是同步的，直接返回这个
    词典对象，这里封装掉"POST 拿 task_id + 轮询"这层差异，让测试写法基本不用变。"""
    resp = await client.post("/api/admin/dictionaries", headers=headers, **kwargs)
    assert resp.status_code == 200, resp.text
    task = await wait_for_task(client, headers, resp.json()["task_id"])
    assert task["status"] == "success", task
    listing = await client.get("/api/admin/dictionaries", headers=headers)
    return next(d for d in listing.json() if d["id"] == task["result"]["dictionary_id"])


async def import_from_dicts_dir(client: AsyncClient, headers: dict[str, str], **kwargs) -> dict:
    """同 import_dictionary，对应 POST /admin/dictionaries/import-from-dicts-dir。"""
    resp = await client.post(
        "/api/admin/dictionaries/import-from-dicts-dir", headers=headers, **kwargs
    )
    assert resp.status_code == 200, resp.text
    task = await wait_for_task(client, headers, resp.json()["task_id"])
    assert task["status"] == "success", task
    listing = await client.get("/api/admin/dictionaries", headers=headers)
    return next(d for d in listing.json() if d["id"] == task["result"]["dictionary_id"])


@pytest.fixture
async def admin_headers(client: AsyncClient) -> dict[str, str]:
    """幂等获取管理员登录态：未初始化则先初始化，已初始化则直接登录。"""
    resp = await client.post(
        "/api/admin/setup", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    )
    if resp.status_code != 200:
        resp = await client.post(
            "/api/admin/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
        )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
