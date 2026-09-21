"""按需把 .spx（Speex）转成浏览器能播的 mp3。

MDict 的发音资源常用 Speex 编码，而浏览器都不支持它——加了 `sound://` 支持之后这些发音
仍然是点不响的。离线脚本（`scripts/transcode_spx.py`）能一次性解决，但用户库里 98.9 万个
.spx 要跑几小时、还要多占几个 G，而真正会听的往往只是很小一部分。

所以这里提供「点哪转哪」：前端请求 `xxx.mp3` 而它不存在时，现场用 ffmpeg 转一个落盘，
下次直接命中。实测单次约 60ms（含 ffmpeg 进程启动），用户基本无感；离线转过的文件在这里
会直接命中、不会被重转，两套方案并存不冲突。

ffmpeg 是**可选依赖**：它通常是 GPL/LGPL 构建，不随这个 MIT 项目的镜像分发。容器里找不到
ffmpeg 时整个功能自动降级——请求照旧 404、前端提示格式不支持，与没有这个模块时完全一致。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger("mydict.spx")

# 与离线脚本保持一致的参数：放音/发音这种短音频，低码率单声道足够
_CODEC_ARGS = ("-c:a", "libmp3lame", "-b:a", "32k", "-ac", "1", "-ar", "22050")

# 判定「已经能播」的产物后缀，与前端播放候选（.mp3 → .opus → 原文件）对齐
_PRODUCT_SUFFIXES = (".mp3", ".opus")

# 单个文件最多等这么久；坏文件可能让 ffmpeg 卡住，不能让它把请求线程一直占着
_TIMEOUT_SECONDS = 15

# 按需转码的同时并发数：多人同时点不同发音时，别让 ffmpeg 把 CPU 吃光、把请求堵住
_MAX_CONCURRENT = 2

# 批量转码（后台任务，管理员显式发起）的并发。比按需高，但也不能太满——容器里 uvicorn
# 是单进程，转码和查询抢同一份 CPU。
_BATCH_MAX_WORKERS = 4

_semaphore = threading.BoundedSemaphore(_MAX_CONCURRENT)
_lock = threading.Lock()
# (ffmpeg 路径, 版本)；None 表示还没探测过。容器里的 ffmpeg 不会中途出现或消失，探一次就够
_probe: tuple[str | None, str | None] | None = None
_converted = 0
_failed = 0


def _detect_ffmpeg() -> tuple[str | None, str | None]:
    path = shutil.which("ffmpeg")
    if path is None:
        return None, None
    try:
        result = subprocess.run(
            [path, "-version"], capture_output=True, text=True, timeout=_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.SubprocessError):
        return None, None
    if result.returncode != 0:
        return None, None
    first_line = (result.stdout or "").splitlines()[0] if result.stdout else ""
    # 形如 "ffmpeg version 8.1.1-mediasrv Copyright (c) ..."
    version = None
    if "version" in first_line:
        version = first_line.split("version", 1)[1].strip().split(" ", 1)[0]
    return path, version


def ffmpeg_path() -> str | None:
    """可用的 ffmpeg 路径；没有则返回 None。只探测一次。"""
    global _probe
    with _lock:
        if _probe is None:
            _probe = _detect_ffmpeg()
        return _probe[0]


def status(refresh: bool = False) -> dict:
    """给管理后台看的运行状态。

    refresh=True 时忽略缓存重新探测。需要这个参数是因为探测结果在进程内只算一次（容器里的
    ffmpeg 不会中途出现），而后台「重新检测」按钮的语义恰恰是「我刚挂上，别看旧结果」。
    """
    global _probe
    with _lock:
        if refresh or _probe is None:
            _probe = _detect_ffmpeg()
        path, version = _probe
        return {
            "available": path is not None,
            "ffmpeg_path": path,
            "ffmpeg_version": version,
            "converted": _converted,
            "failed": _failed,
            "max_concurrent": _MAX_CONCURRENT,
        }


def _run_ffmpeg(ffmpeg: str, source: Path, target: Path) -> bool:
    """调一次 ffmpeg；成功返回 True。

    失败一律把可能留下的半成品删掉——前端拿到 0 字节文件会播放失败，还不如回退到原 .spx。
    这是全模块唯一构造命令行的地方，按需与批量两条路径共用。
    """
    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                *_CODEC_ARGS,
                str(target),
            ],
            capture_output=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        target.unlink(missing_ok=True)
        logger.warning("发音转码失败 %s：%s", source, exc)
        return False

    if result.returncode != 0 or not target.exists() or target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        logger.warning("发音转码失败 %s：%s", source, (result.stderr or b"")[:200])
        return False
    return True


def _has_product(source: Path) -> bool:
    """同名**同目录**下是否已经有可播放的产物。

    必须同名同目录：韦氏大学词典与 The little dict 自带的 mp3 在别的目录（合计 35 万个），
    按「这个目录里有 mp3」判会把它们整体误判成已经转好。
    """
    for suffix in _PRODUCT_SUFFIXES:
        candidate = source.with_suffix(suffix)
        try:
            if candidate.is_file() and candidate.stat().st_size > 0:
                return True
        except OSError:
            continue
    return False


def iter_pending_spx(res_dir: Path) -> Iterator[Path]:
    """递归列出 res_dir 下所有还没有产物的 .spx。

    用 os.walk 而不是顶层 glob：必须递归——`res/SPX/`、`res/SPX_K/`、`res/media/spx/`
    这些子目录里的 .spx 占了大头，只扫顶层会漏掉。
    """
    if not res_dir.is_dir():
        return
    for root, _dirs, files in os.walk(res_dir):
        for name in files:
            if not name.lower().endswith(".spx"):
                continue
            source = Path(root) / name
            if not _has_product(source):
                yield source


def count_pending_spx(res_dir: Path) -> int:
    """数一遍待转数量；res_dir 不存在（跳过了资源导入）时是 0。"""
    return sum(1 for _ in iter_pending_spx(res_dir))


def transcode_to_mp3(source: Path) -> Path | None:
    """把 `source`（.spx）转成同名 .mp3 并返回产物路径；不可用或失败时返回 None。

    这是**按需**路径（前端来要 mp3 而它不存在时触发），受 `_MAX_CONCURRENT` 约束，
    免得几个人同时点发音就把请求线程堵住。批量转码走 `transcode_pending`。
    """
    global _converted, _failed

    ffmpeg = ffmpeg_path()
    if ffmpeg is None:
        return None

    target = source.with_suffix(".mp3")
    if target.exists() and target.stat().st_size > 0:
        return target

    # 并发已满就直接放弃：宁可这次放不了，也不让请求排队等成一串
    if not _semaphore.acquire(timeout=_TIMEOUT_SECONDS):
        return None
    try:
        # 抢到名额后再查一次：排在前面的请求可能刚把它转好了
        if target.exists() and target.stat().st_size > 0:
            return target
        if _run_ffmpeg(ffmpeg, source, target):
            _converted += 1
            return target
        _failed += 1
        return None
    finally:
        _semaphore.release()


def transcode_pending(
    res_dir: Path,
    *,
    on_progress: Callable[[int, int], None] | None = None,
    prune_source: bool = True,
) -> dict:
    """把 res_dir 下所有待转的 .spx 批量转成 mp3，默认转成功后删源。

    与按需转码分开并发模型：这是一次后台任务，不用 `_MAX_CONCURRENT`，改用更大的线程池。
    删源只在**产物确认为非空**之后发生，转码失败的一律保留源文件；删源本身失败（权限、
    句柄占用）只记日志不中断整批——那时发音已经能放了，重扫会把计数算成 0。
    """
    global _converted, _failed

    ffmpeg = ffmpeg_path()
    pending = list(iter_pending_spx(res_dir))
    counters = {"ok": 0, "failed": 0, "prune_failed": 0, "total": len(pending)}
    if ffmpeg is None or not pending:
        return {**counters, "available": ffmpeg is not None}

    total = len(pending)
    done = 0
    with ThreadPoolExecutor(max_workers=_BATCH_MAX_WORKERS) as pool:
        futures = {
            pool.submit(_run_ffmpeg, ffmpeg, source, source.with_suffix(".mp3")): source
            for source in pending
        }
        for future in as_completed(futures):
            source = futures[future]
            done += 1
            try:
                ok = future.result()
            except Exception:  # noqa: BLE001 - 单个文件出错不该中断整批
                ok = False
            if ok:
                counters["ok"] += 1
                _converted += 1
                if prune_source:
                    try:
                        source.unlink(missing_ok=True)
                    except OSError as exc:
                        counters["prune_failed"] += 1
                        logger.warning("转码成功但删除源文件失败 %s：%s", source, exc)
            else:
                counters["failed"] += 1
                _failed += 1
            if on_progress is not None:
                on_progress(done, total)

    return {**counters, "available": True}
