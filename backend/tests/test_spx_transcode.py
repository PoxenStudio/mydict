import os
import stat
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.services import spx_transcode


def _fake_tool(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def fake_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # speexdec <in> <out.wav> / lame [opts...] <in.wav> <out.mp3>：各自把输入拷成输出
    _fake_tool(bin_dir, "speexdec", 'cp "$1" "$2"')
    _fake_tool(bin_dir, "lame", 'for a; do p="$q"; q="$a"; done; cp "$p" "$q"')
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


def test_transcodes_next_to_source(tmp_path: Path, fake_tools: Path) -> None:
    source = tmp_path / "a.spx"
    source.write_bytes(b"speex")

    target = spx_transcode.transcode_to_mp3(source)

    assert target == tmp_path / "a.mp3"
    assert target.read_bytes() == b"speex"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.mp3", "a.spx", "bin"]


def test_failure_leaves_no_partial_file(tmp_path: Path, fake_tools: Path) -> None:
    _fake_tool(fake_tools, "lame", "exit 1")
    source = tmp_path / "a.spx"
    source.write_bytes(b"speex")

    assert spx_transcode.transcode_to_mp3(source) is None
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.spx", "bin"]


def test_missing_tools_disable_transcoding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    source = tmp_path / "a.spx"
    source.write_bytes(b"speex")

    assert spx_transcode.transcode_to_mp3(source) is None


async def test_dict_res_serves_transcoded_mp3(client: AsyncClient, fake_tools: Path) -> None:
    res_dir = Path(get_settings().dictionary_storage_path) / "990" / "res" / "snd"
    res_dir.mkdir(parents=True)
    (res_dir / "word.spx").write_bytes(b"speex")

    resp = await client.get("/dict-res/990/res/snd/word.mp3")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert (res_dir / "word.mp3").is_file()


async def test_dict_res_mp3_without_spx_is_404(client: AsyncClient, fake_tools: Path) -> None:
    resp = await client.get("/dict-res/991/res/none.mp3")
    assert resp.status_code == 404
