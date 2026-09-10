import os
import tempfile
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

_tmp_dir = tempfile.mkdtemp(prefix="mydict-test-")
os.environ["DATABASE_PATH"] = os.path.join(_tmp_dir, "db", "mydict.sqlite3")
os.environ["CONFIG_STORAGE_PATH"] = os.path.join(_tmp_dir, "config")
os.environ["DICTS_INBOX_PATH"] = os.path.join(_tmp_dir, "dicts")
os.environ["DICTIONARY_STORAGE_PATH"] = os.path.join(_tmp_dir, "dictionaries")

# 导入 app 会触发 ensure_data_dirs() + run_migrations()，
# 建表与 system_settings 默认值播种均由 Alembic migration 完成，无需在测试里重复处理。
from app.main import app  # noqa: E402


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
