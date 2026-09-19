#!/usr/bin/env python3
"""把 MDict 引擎版本 < 2.0（LZO 压缩块）的老词典导出成 ECDICT 风格 CSV，供后台导入。

背景：mydict 依赖的 mdict-utils 只在额外装了 python-lzo 时才支持 LZO 压缩块，否则遇到这类
词典会直接抛 RuntimeError("LZO compression is not supported")（导入时表现为「服务器内部错误」）。
判断依据是 MDict 文件头里的 GeneratedByEngineVersion：zlib 是引擎 2.0+ 才用的，更老的用 LZO。

而 python-lzo 与它依赖的 liblzo2 都是 GPL，引入 MIT 授权的本项目会造成许可证混用，所以这类
老词典改为**离线**转换：本脚本是一次性运维工具，不属于 MyDict 运行时代码，只有运行它才需要
python-lzo。

用法：

    pip install python-lzo mdict-utils
    python scripts/mdict_lzo_to_ecdict.py \
        --source "/path/to/词典A" "/path/to/词典B" \
        --out-dir ./out

产出：源目录下每个 .mdx 对应一份 CSV（文件名取 .mdx 的主干），字段是标准 ECDICT 的
word/phonetic/definition/translation/pos/collins/oxford/tag/bnc/frq/exchange/detail/audio，
本脚本只填 word（词头）与 definition（原始释义，HTML 原样保留），其余留空。导入走后台
「导入词典 → ECDICT」通道（一次只能选一个 CSV）。

注意：
- 只导出词条正文，.mdd 里的图片/发音不会带上，释义里指向它们的引用会失效。
- 导入时 EcdictParser 会把释义里字面的 "\\n" 两个字符转成真换行，原文若含该序列会被改写。
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Iterator
from pathlib import Path

CSV_FIELDNAMES = [
    "word",
    "phonetic",
    "definition",
    "translation",
    "pos",
    "collins",
    "oxford",
    "tag",
    "bnc",
    "frq",
    "exchange",
    "detail",
    "audio",
]


def iter_mdict_entries(mdx_path: Path) -> Iterator[tuple[str, str]]:
    """逐个产出 (词头, 释义)。释义保持原始 HTML，不做任何改写。"""
    from mdict_utils.base.readmdict import MDX

    mdx = MDX(str(mdx_path))
    for key, value in mdx.items():
        word = key.decode("utf-8", errors="replace").strip()
        if not word:
            continue
        yield word, value.decode("utf-8", errors="replace")


def convert(mdx_path: Path, out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8", newline="") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for word, definition in iter_mdict_entries(mdx_path):
            row = dict.fromkeys(CSV_FIELDNAMES, "")
            row["word"] = word
            row["definition"] = definition
            writer.writerow(row)
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--source",
        required=True,
        nargs="+",
        help="含 .mdx 的目录（其中每个 .mdx 各转一份）或单个 .mdx 文件，可传多个",
    )
    parser.add_argument("--out-dir", default="./out", help="CSV 输出目录")
    args = parser.parse_args()

    try:
        import lzo  # noqa: F401
    except ImportError:
        print(
            "缺少 python-lzo（GPL，仅本离线工具需要）：请先 pip install python-lzo",
            file=sys.stderr,
        )
        raise SystemExit(1)

    mdx_files: list[Path] = []
    for raw in args.source:
        source = Path(raw)
        if source.is_dir():
            mdx_files.extend(sorted(source.rglob("*.mdx")))
        elif source.is_file():
            mdx_files.append(source)
        else:
            print(f"路径不存在：{source}", file=sys.stderr)
            raise SystemExit(1)

    if not mdx_files:
        print("未找到任何 .mdx", file=sys.stderr)
        raise SystemExit(1)

    out_dir = Path(args.out_dir)
    total = 0
    for mdx_path in mdx_files:
        out_path = out_dir / f"{mdx_path.stem}.csv"
        count = convert(mdx_path, out_path)
        total += count
        print(f"{mdx_path} -> {out_path}（{count} 条）")

    print(f"完成：{len(mdx_files)} 个词典，共 {total} 条词条，输出目录 {out_dir}")


if __name__ == "__main__":
    main()
