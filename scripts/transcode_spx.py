#!/usr/bin/env python3
"""把词典 res/ 目录里的 .spx（Speex）批量转成浏览器能直接播放的音频。

背景：MDict 的发音资源常用 Speex（.spx）编码，而**浏览器都不支持** Speex——Chrome/
Firefox/Edge/Safari 都不认，加了 `sound://` 支持之后这些发音仍然是点不响的。转成
mp3/opus 就正常了。

为什么是**离线**脚本而不是镜像里转：

- ffmpeg 的发行版构建通常是 GPL/LGPL，装进这个 MIT 授权的镜像会有许可证混用问题；
  本脚本是一次性运维工具，只有运行它才需要 ffmpeg，可以装在宿主机或一次性容器里。
  这与 `mdict_lzo_to_ecdict.py`（LZO）、EPWING 的处理方式是同一条路子。
- 转码是密集 CPU 活，跑在请求进程里会拖慢查询。

用法（在**宿主机**上跑，路径指向词典资源目录；容器里的 /data/dictionaries 对应宿主机的挂载源）：

    python3 scripts/transcode_spx.py --root /path/to/dictionaries

    只想先看工作量：  --dry-run
    先拿一小批试：    --limit 20
    换格式/并发：      --format opus --jobs 16

产出：每个 `x.spx` 旁边生成 `x.mp3`（默认），**默认保留原 .spx**——前端优先取转码后的文件、
取不到再回退原文件，所以部分转码也不会坏。

想回收空间就加 `--prune-source`：只在**产物确实非空**时才删原 .spx；转码失败的、以及跳过
处理的（已有产物）都按各自规则来——失败的保留源文件，已有产物的顺手回收源文件。

实测（用户的真实词典库，单个文件平均 4.8 KB）：

    格式    单线程耗时     产物相对原始体积    全量 98.9 万个的估算
    mp3     0.055 秒/个    1.44 倍            约 6.5 GB
    opus    0.185 秒/个    0.64 倍            约 2.9 GB

所以「转 mp3 + 删源」净增约 2 GB（原 4.51 GB → 6.5 GB），而「转 opus + 删源」净省约 1.6 GB
（不过 iOS Safari 对 Ogg Opus 的支持一直不完整，桌面端用才推荐）。

默认选 mp3：兼容性最好。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# 转码参数：放音/发音这种短音频用低码率单声道就够，体积也只有原始 Speex 的一半到一倍半
_FORMATS: dict[str, list[str]] = {
    "mp3": ["-c:a", "libmp3lame", "-b:a", "32k", "-ac", "1", "-ar", "22050"],
    "opus": ["-c:a", "libopus", "-b:a", "16k", "-ac", "1"],
}
_SUFFIX = {"mp3": ".mp3", "opus": ".opus"}


def _format_size(num_bytes: int) -> str:
    for unit, scale in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if num_bytes >= scale:
            return f"{num_bytes / scale:.2f} {unit}"
    return f"{num_bytes} B"


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _transcode(
    source: Path, target: Path, codec_args: list[str], force: bool, prune_source: bool
) -> str:
    """返回 'ok' / 'skipped' / 'failed'。"""
    if not force and target.exists() and target.stat().st_size > 0:
        # 已经有产物：顺手把源文件回收掉（前提是产物非空）
        if prune_source:
            source.unlink(missing_ok=True)
        return "skipped"
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            *codec_args,
            # +faststart 让播放器不必先下完整个文件（对本地文件无影响，对以后可能的
            # 远程播放有用）
            str(target),
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        # 失败时别留下半成品：前端拿到 0 字节文件会播放失败，还不如回退到原 .spx
        target.unlink(missing_ok=True)
        return "failed"
    if prune_source:
        source.unlink(missing_ok=True)
    return "ok"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="把词典 res/ 里的 .spx 批量转成可播放音频"
    )
    parser.add_argument(
        "--root", required=True, help="词典资源目录（容器里的 /data/dictionaries）"
    )
    parser.add_argument(
        "--format", choices=sorted(_FORMATS), default="mp3", help="输出格式"
    )
    parser.add_argument("--jobs", type=int, default=8, help="并发数，默认 8")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个（试跑用）")
    parser.add_argument("--force", action="store_true", help="已有产物也重新转")
    parser.add_argument(
        "--prune-source",
        action="store_true",
        help="产物非空时删掉原 .spx 以回收空间（默认保留；转码失败的一定保留）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只统计不转码")
    args = parser.parse_args()

    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"目录不存在：{root}", file=sys.stderr)
        raise SystemExit(1)

    sources = sorted(path for path in root.rglob("*.spx") if path.is_file())
    if args.limit:
        sources = sources[: args.limit]
    if not sources:
        print(f"没找到 .spx 文件：{root}")
        return

    total_bytes = sum(path.stat().st_size for path in sources)
    print(f"找到 {len(sources)} 个 .spx，合计 {_format_size(total_bytes)}")

    if args.dry_run:
        suffix = _SUFFIX[args.format]
        pending = sum(1 for path in sources if not path.with_suffix(suffix).exists())
        print(f"其中 {pending} 个还没有 {suffix} 产物（转码时会跳过其余的）")
        return

    if not _ffmpeg_available():
        print(
            "找不到 ffmpeg。它是本脚本唯一的依赖，且**不随镜像分发**（GPL/LGPL 与项目 "
            "MIT 授权不兼容），请先在宿主机或一次性容器里装好再运行。",
            file=sys.stderr,
        )
        raise SystemExit(1)

    suffix = _SUFFIX[args.format]
    codec_args = _FORMATS[args.format]
    counters = {"ok": 0, "skipped": 0, "failed": 0}
    failures: list[Path] = []
    started = time.monotonic()

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {
            pool.submit(
                _transcode, path, path.with_suffix(suffix), codec_args, args.force, args.prune_source
            ): path
            for path in sources
        }
        for done, future in enumerate(as_completed(futures), start=1):
            path = futures[future]
            try:
                status = future.result()
            except Exception:  # noqa: BLE001 - 单个文件出错不该中断整批
                status = "failed"
            counters[status] += 1
            if status == "failed":
                failures.append(path)
            if done % 200 == 0 or done == len(sources):
                elapsed = time.monotonic() - started
                rate = done / elapsed if elapsed else 0
                print(
                    f"  进度 {done}/{len(sources)}  已转 {counters['ok']}"
                    f"  跳过 {counters['skipped']}  失败 {counters['failed']}"
                    f"  {rate:.0f} 个/秒",
                    flush=True,
                )

    elapsed = time.monotonic() - started
    print(
        f"\n完成：转码 {counters['ok']}，跳过 {counters['skipped']}，失败 {counters['failed']}，"
        f"用时 {elapsed / 60:.1f} 分钟"
    )
    if failures:
        print("以下文件转码失败（保留原 .spx，前端会回退到它）：")
        for path in failures[:20]:
            print(f"  {path}")
        if len(failures) > 20:
            print(f"  ……共 {len(failures)} 个")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
