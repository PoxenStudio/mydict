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
