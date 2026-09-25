from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core import bootstrap, migrate
from app.core.config import get_settings
from app.services.background_task_service import background_tasks


@pytest.fixture
def isolated_phase(monkeypatch) -> None:
    """用例里会改启动阶段，结束后由 monkeypatch 还原成 READY，不影响其它用例。"""
    monkeypatch.setattr(bootstrap, "_phase", bootstrap._phase)
    monkeypatch.setattr(bootstrap, "_message", bootstrap._message)


@pytest.fixture
def scratch_db(tmp_path: Path, monkeypatch) -> Path:
    database = tmp_path / "bootstrap.sqlite3"
    monkeypatch.setattr(get_settings(), "database_path", str(database))
    return database


async def test_status_when_ready(client: AsyncClient) -> None:
    resp = await client.get("/api/system/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["phase"] == "ready" and body["blocking"] is False
    assert body["tasks"] == [] and body["busy_notice"] is None


async def test_gate_blocks_business_api_until_ready(client: AsyncClient, isolated_phase) -> None:
    bootstrap._set(bootstrap.Phase.MIGRATING, "正在升级数据库")

    resp = await client.get("/api/public/settings")
    assert resp.status_code == 503
    assert resp.json()["code"] == "maintenance"
    assert resp.headers["Retry-After"]

    assert (await client.get("/api/health")).status_code == 200
    status = (await client.get("/api/system/status")).json()
    assert status["phase"] == "migrating" and status["blocking"] is True
    assert status["message"] == "正在升级数据库"

    bootstrap._set(bootstrap.Phase.READY, None)
    assert (await client.get("/api/public/settings")).status_code == 200


async def test_status_hides_private_task_details(client: AsyncClient) -> None:
    task = background_tasks.start("dictionary_reparse", "某部词典")
    try:
        body = (await client.get("/api/system/status")).json()
        assert body["tasks"] == []
        assert body["busy_notice"] and "某部词典" not in body["busy_notice"]
    finally:
        background_tasks.succeed(task.id, {})


def test_run_migrates_then_ready(scratch_db: Path, isolated_phase) -> None:
    bootstrap._set(bootstrap.Phase.STARTING, None)
    bootstrap.run()
    assert bootstrap.snapshot() == (bootstrap.Phase.READY, None)
    assert migrate.pending_migrations() == []


def test_run_reports_public_migration_progress(scratch_db: Path, isolated_phase, monkeypatch):
    seen: list[dict] = []

    def fake_run(pending, on_step):
        on_step(1, pending[0])
        seen.extend(t for t in background_tasks.list_running() if t["public"])

    monkeypatch.setattr(migrate, "run_migrations", fake_run)
    bootstrap.run()

    assert seen[0]["task_type"] == "system_migration"
    assert seen[0]["progress_data"]["done"] == 0
    assert seen[0]["progress_data"]["total"] == len(migrate.pending_migrations())
    assert bootstrap.is_ready()


def test_run_stays_failed_when_disk_is_short(scratch_db: Path, isolated_phase, monkeypatch):
    monkeypatch.setattr(migrate, "free_space_for_database", lambda: (10, 1))
    monkeypatch.setattr(
        migrate,
        "pending_migrations",
        lambda: [migrate.PendingMigration("x", "重建", heavy=True)],
    )
    bootstrap.run()
    phase, message = bootstrap.snapshot()
    assert phase is bootstrap.Phase.FAILED and "磁盘空间" in message


def test_run_hides_exception_details_on_failure(scratch_db: Path, isolated_phase, monkeypatch):
    def boom(pending, on_step):
        raise RuntimeError("/data/db/mydict.sqlite3 损坏")

    monkeypatch.setattr(migrate, "run_migrations", boom)
    bootstrap.run()
    phase, message = bootstrap.snapshot()
    assert phase is bootstrap.Phase.FAILED
    assert "/data" not in message and "日志" in message
