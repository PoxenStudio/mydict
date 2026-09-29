"""按需把 .spx（Speex）转成同名 .mp3：speexdec → WAV → lame。

浏览器原生放不了 Speex；前端先要 `x.mp3`，不存在时在这里现转一个落盘，下次直接命中。
先落 WAV 再交给 lame：同一部词典里的 spx 采样率并不一致（32k/48k 都有），lame 需要读
WAV 头拿到真实采样率。speexdec / lame 缺失时整个功能关闭，请求照旧 404。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

logger = logging.getLogger("mydict.spx")

_LAME_ARGS = ("--quiet", "-m", "m", "-b", "32", "--resample", "22.05")
_TIMEOUT_SECONDS = 15
_semaphore = threading.BoundedSemaphore(2)


def _run(args: list[str]) -> bool:
    try:
        return subprocess.run(args, capture_output=True, timeout=_TIMEOUT_SECONDS).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def transcode_to_mp3(source: Path) -> Path | None:
    """把 `source` 转成同目录同名 .mp3 并返回；工具缺失或转码失败返回 None。"""
    speexdec, lame = shutil.which("speexdec"), shutil.which("lame")
    if speexdec is None or lame is None:
        return None

    target = source.with_suffix(".mp3")
    if not _semaphore.acquire(timeout=_TIMEOUT_SECONDS):
        return None
    try:
        # 排队期间可能已被别的请求转好
        if target.is_file() and target.stat().st_size > 0:
            return target
        with tempfile.TemporaryDirectory(dir=source.parent, prefix=".spx-") as work:
            wav, mp3 = Path(work) / "a.wav", Path(work) / "a.mp3"
            ok = (
                _run([speexdec, str(source), str(wav)])
                and _run([lame, *_LAME_ARGS, str(wav), str(mp3)])
                and mp3.is_file()
                and mp3.stat().st_size > 0
            )
            if not ok:
                logger.warning("spx transcode failed: %s", source)
                return None
            os.replace(mp3, target)
        return target
    finally:
        _semaphore.release()
