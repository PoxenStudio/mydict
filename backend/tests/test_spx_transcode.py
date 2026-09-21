"""发音按需转码（.spx → .mp3）的用例。

ffmpeg 在测试机上是可选的（它不随镜像分发），而且宿主机那个构建只支持 speex **解码**、
不支持编码，造不出真实的 .spx。所以这里把 subprocess.run 换成「写一个假 mp3」，
验证的是判断逻辑本身：什么时候该转、什么时候该老实 404、失败了怎么收场。
"""

import csv
import io
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.services import spx_transcode
from app.services.settings_service import set_setting
from tests.conftest import import_dictionary, wait_for_task


class _FakeCompleted:
    def __init__(self, returncode: int = 0, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stderr = stderr


@pytest.fixture(autouse=True)
def _reset_probe():
    """`_probe` 是模块级缓存（容器里的 ffmpeg 不会中途出现），用例之间会互相污染。"""
    spx_transcode._probe = None
    yield
    spx_transcode._probe = None


def _with_ffmpeg(monkeypatch, *, returncode: int = 0) -> list[list[str]]:
    """假装容器里有 ffmpeg，并把每次调用记录下来。"""
    calls: list[list[str]] = []
    monkeypatch.setattr(spx_transcode, "_probe", ("/usr/bin/ffmpeg", "8.1.1"))

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        if returncode == 0:
            # ffmpeg 的最后一个参数就是输出路径
            Path(cmd[-1]).write_bytes(b"fake-mp3")
        return _FakeCompleted(returncode, b"boom")

    monkeypatch.setattr(spx_transcode.subprocess, "run", fake_run)
    return calls


def _without_ffmpeg(monkeypatch) -> None:
    monkeypatch.setattr(spx_transcode, "_probe", (None, None))


def _make_spx(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake-speex")
    return path


# --------------------------------------------------------------------- 纯函数


def test_transcode_returns_none_without_ffmpeg(tmp_path: Path, monkeypatch) -> None:
    """容器里没有 ffmpeg 就什么都不做——这是这套功能「可选」的关键。"""
    _without_ffmpeg(monkeypatch)
    source = _make_spx(tmp_path / "a.spx")

    assert spx_transcode.transcode_to_mp3(source) is None
    assert not (tmp_path / "a.mp3").exists()


def test_transcode_writes_mp3(tmp_path: Path, monkeypatch) -> None:
    calls = _with_ffmpeg(monkeypatch)
    source = _make_spx(tmp_path / "a.spx")

    result = spx_transcode.transcode_to_mp3(source)

    assert result == tmp_path / "a.mp3"
    assert result is not None and result.stat().st_size > 0
    assert len(calls) == 1
    assert calls[0][-1] == str(tmp_path / "a.mp3")


def test_transcode_reuses_existing_mp3(tmp_path: Path, monkeypatch) -> None:
    """已经有产物就直接用：离线脚本转过的文件不该被重转一遍。"""
    calls = _with_ffmpeg(monkeypatch)
    source = _make_spx(tmp_path / "a.spx")
    (tmp_path / "a.mp3").write_bytes(b"already-there")

    assert spx_transcode.transcode_to_mp3(source) == tmp_path / "a.mp3"
    assert calls == []


def test_transcode_leaves_no_half_product_on_failure(tmp_path: Path, monkeypatch) -> None:
    """失败不能留下 0 字节文件——前端拿到它会播放失败，还不如回退到原 .spx。"""
    _with_ffmpeg(monkeypatch, returncode=1)
    source = _make_spx(tmp_path / "a.spx")

    assert spx_transcode.transcode_to_mp3(source) is None
    assert not (tmp_path / "a.mp3").exists()


# ----------------------------------------------------------------------- 接口


async def test_dict_res_transcodes_missing_mp3(
    client: AsyncClient, admin_headers: dict[str, str], monkeypatch
) -> None:
    """前端来要 mp3 而它不存在、但同名 .spx 在场时，现转一个给它。"""
    _with_ffmpeg(monkeypatch)
    res_dir = Path(get_settings().dictionary_storage_path) / "4242" / "res" / "SPX"
    _make_spx(res_dir / "0001.spx")

    resp = await client.get("/dict-res/4242/res/SPX/0001.mp3")

    assert resp.status_code == 200, resp.text
    assert (res_dir / "0001.mp3").exists()


async def test_dict_res_404_without_ffmpeg(
    client: AsyncClient, admin_headers: dict[str, str], monkeypatch
) -> None:
    """没挂 ffmpeg 时行为与没有这个功能时完全一致：404，前端照旧回退提示。"""
    _without_ffmpeg(monkeypatch)
    res_dir = Path(get_settings().dictionary_storage_path) / "4243" / "res" / "SPX"
    _make_spx(res_dir / "0001.spx")

    resp = await client.get("/dict-res/4243/res/SPX/0001.mp3")

    assert resp.status_code == 404


async def test_dict_res_404_when_switch_off(
    client: AsyncClient, admin_headers: dict[str, str], db_session, monkeypatch
) -> None:
    """挂了 ffmpeg 但开关关掉时不转。"""
    calls = _with_ffmpeg(monkeypatch)
    set_setting(db_session, "spx_online_transcode", "false")
    res_dir = Path(get_settings().dictionary_storage_path) / "4244" / "res" / "SPX"
    _make_spx(res_dir / "0001.spx")

    resp = await client.get("/dict-res/4244/res/SPX/0001.mp3")

    assert resp.status_code == 404
    assert calls == []


async def test_dict_res_404_when_source_missing(
    client: AsyncClient, admin_headers: dict[str, str], monkeypatch
) -> None:
    """连 .spx 都没有的普通缺失，不该去惊动 ffmpeg。"""
    calls = _with_ffmpeg(monkeypatch)

    resp = await client.get("/dict-res/4245/res/SPX/nothing.mp3")

    assert resp.status_code == 404
    assert calls == []


async def test_spx_status_endpoint(
    client: AsyncClient, admin_headers: dict[str, str], monkeypatch
) -> None:
    """设置页要拿这个来看「容器里到底有没有 ffmpeg」。"""
    _with_ffmpeg(monkeypatch)

    resp = await client.get("/api/admin/settings/spx-transcode", headers=admin_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["available"] is True
    assert body["ffmpeg_version"] == "8.1.1"
    assert body["max_concurrent"] >= 1


async def test_spx_status_reports_unavailable(
    client: AsyncClient, admin_headers: dict[str, str], monkeypatch
) -> None:
    _without_ffmpeg(monkeypatch)

    resp = await client.get("/api/admin/settings/spx-transcode", headers=admin_headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["available"] is False


async def test_spx_status_requires_admin(client: AsyncClient) -> None:
    resp = await client.get("/api/admin/settings/spx-transcode")
    assert resp.status_code == 401


# ----------------------------------------------------------------- 检测判据


def test_count_pending_ignores_files_with_product(tmp_path: Path) -> None:
    """有同名产物就不算待转；判据与前端播放候选一致（.mp3 或 .opus 都算）。"""
    _make_spx(tmp_path / "a.spx")
    _make_spx(tmp_path / "b.spx")
    (tmp_path / "b.mp3").write_bytes(b"done")
    _make_spx(tmp_path / "c.spx")
    (tmp_path / "c.opus").write_bytes(b"done")

    assert spx_transcode.count_pending_spx(tmp_path) == 1  # 只剩 a


def test_count_pending_scans_subdirectories(tmp_path: Path) -> None:
    """必须递归：res/SPX/ 这类子目录里的 .spx 占大头，只扫顶层会漏掉。"""
    _make_spx(tmp_path / "SPX" / "deep.spx")
    _make_spx(tmp_path / "media" / "spx" / "deeper.spx")
    _make_spx(tmp_path / "top.spx")

    assert spx_transcode.count_pending_spx(tmp_path) == 3


def test_count_pending_requires_same_directory_product(tmp_path: Path) -> None:
    """产物必须与源**同名同目录**——词典自带的 mp3 常在别的目录，按「目录里有 mp3」判会误判。"""
    _make_spx(tmp_path / "spx" / "x.spx")
    (tmp_path / "pron").mkdir(parents=True)
    (tmp_path / "pron" / "x.mp3").write_bytes(b"self-contained audio, not a transcode")

    assert spx_transcode.count_pending_spx(tmp_path) == 1


def test_count_pending_ignores_empty_product(tmp_path: Path) -> None:
    """0 字节产物等于没转——前端拿到它会播放失败。"""
    _make_spx(tmp_path / "a.spx")
    (tmp_path / "a.mp3").write_bytes(b"")

    assert spx_transcode.count_pending_spx(tmp_path) == 1


def test_count_pending_missing_dir(tmp_path: Path) -> None:
    """跳过资源导入的词典根本没有 res/，算 0 而不是报错。"""
    assert spx_transcode.count_pending_spx(tmp_path / "nope") == 0


# ----------------------------------------------------------------- 批量转码


def test_transcode_pending_prunes_source(tmp_path: Path, monkeypatch) -> None:
    _with_ffmpeg(monkeypatch)
    _make_spx(tmp_path / "a.spx")
    _make_spx(tmp_path / "b.spx")

    result = spx_transcode.transcode_pending(tmp_path)

    assert result["ok"] == 2
    assert result["total"] == 2
    # 转成功就删源（用户明确要求；源词典文件有备份）
    assert not (tmp_path / "a.spx").exists()
    assert not (tmp_path / "b.spx").exists()
    assert (tmp_path / "a.mp3").exists()


def test_transcode_pending_keeps_source_on_failure(tmp_path: Path, monkeypatch) -> None:
    """失败要保留源文件——前端还要回退到它。"""
    _with_ffmpeg(monkeypatch, returncode=1)
    _make_spx(tmp_path / "a.spx")

    result = spx_transcode.transcode_pending(tmp_path)

    assert result["failed"] == 1
    assert (tmp_path / "a.spx").exists()
    assert not (tmp_path / "a.mp3").exists()


def test_transcode_pending_reports_progress(tmp_path: Path, monkeypatch) -> None:
    _with_ffmpeg(monkeypatch)
    for name in ("a", "b", "c"):
        _make_spx(tmp_path / f"{name}.spx")
    seen: list[tuple[int, int]] = []

    spx_transcode.transcode_pending(
        tmp_path, on_progress=lambda done, total: seen.append((done, total))
    )

    assert sorted(done for done, _ in seen) == [1, 2, 3]
    assert all(total == 3 for _, total in seen)


def test_transcode_pending_without_ffmpeg(tmp_path: Path, monkeypatch) -> None:
    """没 ffmpeg 时整批不动，源文件一个都不能少。"""
    _without_ffmpeg(monkeypatch)
    _make_spx(tmp_path / "a.spx")

    result = spx_transcode.transcode_pending(tmp_path)

    assert result["available"] is False
    assert (tmp_path / "a.spx").exists()


# ----------------------------------------------------------------- 重新检测


def test_status_refresh_redetects(monkeypatch) -> None:
    """后台「重新检测」按钮靠这个：探测结果默认进程内只算一次，挂上 ffmpeg 后不刷新永远不变。"""
    _without_ffmpeg(monkeypatch)
    assert spx_transcode.status()["available"] is False

    monkeypatch.setattr(spx_transcode, "_detect_ffmpeg", lambda: ("/usr/bin/ffmpeg", "9.9.9"))
    # 不刷新时仍是缓存里的旧结果
    assert spx_transcode.status()["available"] is False
    # 刷新后拿到新结果，且缓存被更新
    assert spx_transcode.status(refresh=True)["available"] is True
    assert spx_transcode.status()["ffmpeg_version"] == "9.9.9"


async def test_spx_status_refresh_param(
    client: AsyncClient, admin_headers: dict[str, str], monkeypatch
) -> None:
    _without_ffmpeg(monkeypatch)
    first = await client.get("/api/admin/settings/spx-transcode", headers=admin_headers)
    assert first.json()["available"] is False

    monkeypatch.setattr(spx_transcode, "_detect_ffmpeg", lambda: ("/usr/bin/ffmpeg", "9.9.9"))
    refreshed = await client.get(
        "/api/admin/settings/spx-transcode",
        params={"refresh": "true"},
        headers=admin_headers,
    )
    assert refreshed.json()["available"] is True


# ------------------------------------------------------- 导入检测与后台任务


def _csv_bytes() -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["word", "definition", "translation", "exchange"])
    writer.writeheader()
    writer.writerow({"word": "entryword", "definition": "a word", "translation": "释义"})
    return buf.getvalue().encode("utf-8")


async def _make_dictionary(
    client: AsyncClient, admin_headers: dict[str, str], name: str
) -> int:
    dictionary = await import_dictionary(
        client,
        admin_headers,
        data={"name": name, "format": "ecdict", "lang_from": "en", "lang_to": "zh"},
        files={"files": (f"{name}.csv", _csv_bytes(), "text/csv")},
    )
    return dictionary["id"]


async def test_import_marks_spx_scanned(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """导入收尾会跑一次发音资源检测。

    ecdict 没有发音资源，所以计数是 0；但时间戳必须有值——「扫过、没有」与「还没扫过」
    是两种状态，升级前导入的存量词典正是后者（NULL）。
    """
    dict_id = await _make_dictionary(client, admin_headers, "导入检测")

    resp = await client.get("/api/admin/dictionaries", headers=admin_headers)
    item = next(d for d in resp.json() if d["id"] == dict_id)
    assert item["spx_pending_count"] == 0
    assert item["spx_scanned_at"] is not None


async def test_scan_spx_backfills_counts(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """存量词典靠这个端点回填——没有它，升级前导入的词典永远不显示「需转码」。"""
    dict_id = await _make_dictionary(client, admin_headers, "扫描回填")
    res_dir = Path(get_settings().dictionary_storage_path) / str(dict_id) / "res"
    _make_spx(res_dir / "a.spx")
    _make_spx(res_dir / "SPX" / "b.spx")  # 子目录里的也要算
    _make_spx(res_dir / "c.spx")
    (res_dir / "c.mp3").write_bytes(b"done")  # 已有产物的不算

    started = await client.post(
        "/api/admin/dictionaries/scan-spx",
        headers=admin_headers,
        json={"dictionary_ids": [dict_id]},
    )
    assert started.status_code == 200, started.text
    task = await wait_for_task(client, admin_headers, started.json()["task_id"])
    assert task["status"] == "success", task

    listing = await client.get("/api/admin/dictionaries", headers=admin_headers)
    item = next(d for d in listing.json() if d["id"] == dict_id)
    assert item["spx_pending_count"] == 2  # a + SPX/b


async def test_transcode_without_ffmpeg_is_rejected(
    client: AsyncClient, admin_headers: dict[str, str], monkeypatch
) -> None:
    """没 ffmpeg 时直接报错，而不是登记一个注定失败的任务。"""
    _without_ffmpeg(monkeypatch)
    dict_id = await _make_dictionary(client, admin_headers, "缺 ffmpeg")

    resp = await client.post(
        "/api/admin/dictionaries/transcode-spx",
        headers=admin_headers,
        json={"dictionary_ids": [dict_id]},
    )

    assert resp.status_code == 422
    running = await client.get("/api/admin/tasks/running", headers=admin_headers)
    assert running.json() == []


async def test_transcode_endpoint_prunes_spx(
    client: AsyncClient, admin_headers: dict[str, str], monkeypatch
) -> None:
    """转码成功后删掉原 .spx，并把新的待转数写回词典记录。"""
    _with_ffmpeg(monkeypatch)
    dict_id = await _make_dictionary(client, admin_headers, "转码删源")
    res_dir = Path(get_settings().dictionary_storage_path) / str(dict_id) / "res"
    _make_spx(res_dir / "a.spx")
    _make_spx(res_dir / "b.spx")

    started = await client.post(
        "/api/admin/dictionaries/transcode-spx",
        headers=admin_headers,
        json={"dictionary_ids": [dict_id]},
    )
    assert started.status_code == 200, started.text
    task = await wait_for_task(client, admin_headers, started.json()["task_id"])
    assert task["status"] == "success", task
    assert task["result"]["ok"] == 2

    assert not (res_dir / "a.spx").exists()
    assert (res_dir / "a.mp3").exists()

    listing = await client.get("/api/admin/dictionaries", headers=admin_headers)
    item = next(d for d in listing.json() if d["id"] == dict_id)
    assert item["spx_pending_count"] == 0


async def test_spx_endpoints_require_admin(client: AsyncClient) -> None:
    for path, body in (
        ("/api/admin/dictionaries/scan-spx", {}),
        ("/api/admin/dictionaries/transcode-spx", {"dictionary_ids": [1]}),
    ):
        resp = await client.post(path, json=body)
        assert resp.status_code == 401, path
