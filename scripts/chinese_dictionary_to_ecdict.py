#!/usr/bin/env python3
"""把 mapull/chinese-dictionary 语料转换为两份 ECDICT 风格 CSV，供后台导入。

一次性离线脚本，不属于 MyDict 运行时代码，用法：

    python scripts/chinese_dictionary_to_ecdict.py \
        --source /path/to/chinese-dictionary \
        --out-dir ./out

产出：
    out/汉语字典.csv   —— 单字，来自 character/char_detail.json（+ char_base.json/related.json 补充结构化信息）
    out/汉语词典.csv   —— 词语/成语，来自 word/word.json（+ idiom/idiom.json 按词精确匹配增强）

两份 CSV 均是标准 ECDICT 字段（word/phonetic/definition/translation/pos/collins/oxford/
tag/bnc/frq/exchange/detail/audio），中文语料只用到 word/phonetic/translation/detail，
其余字段留空；detail 列写入结构化 JSON，供导入时透传合并进 dict_entries.extra。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Iterator

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


def _empty_row(
    word: str, phonetic: str, translation: str, detail: dict[str, Any] | None
) -> dict[str, str]:
    row = dict.fromkeys(CSV_FIELDNAMES, "")
    row["word"] = word
    row["phonetic"] = phonetic
    row["translation"] = translation
    row["detail"] = json.dumps(detail, ensure_ascii=False) if detail else ""
    return row


def iter_ndjson_no_brackets(path: Path) -> Iterator[dict[str, Any]]:
    """character/char_base.json、char_detail.json 等：每行一个 JSON 对象，行尾带逗号，无外层 []。"""
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.endswith(","):
                line = line[:-1]
            yield json.loads(line)


def load_json_array(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def format_char_translation(entry: dict[str, Any]) -> str:
    """把 char_detail.json 的 pronunciations/explanations 整理成多行可读释义。"""
    lines = []
    for pron in entry.get("pronunciations", []):
        pinyin = pron.get("pinyin", "")
        senses = []
        for exp in pron.get("explanations", []):
            content = exp.get("content", "").strip()
            if not content:
                continue
            speech = exp.get("speech")
            senses.append(f"({speech}) {content}" if speech else content)
        if senses:
            lines.append(f"[{pinyin}] " + "；".join(senses))
    return "\n".join(lines)


def build_char_dictionary(source: Path, out_path: Path) -> int:
    char_base_path = source / "character" / "char_base.json"
    char_detail_path = source / "character" / "char_detail.json"
    related_path = source / "character" / "related.json"

    base_by_char: dict[str, dict[str, Any]] = {
        item["char"]: item for item in iter_ndjson_no_brackets(char_base_path)
    }
    related_by_char: dict[str, dict[str, Any]] = {
        item["char"]: item for item in load_json_array(related_path)
    }

    count = 0
    with out_path.open("w", encoding="utf-8", newline="") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for entry in iter_ndjson_no_brackets(char_detail_path):
            char = entry.get("char")
            if not char:
                continue
            base = base_by_char.get(char, {})
            related = related_by_char.get(char, {})
            pinyin_list = base.get("pinyin") or [
                p.get("pinyin")
                for p in entry.get("pronunciations", [])
                if p.get("pinyin")
            ]
            detail = {
                k: v
                for k, v in {
                    "strokes": base.get("strokes"),
                    "radicals": base.get("radicals"),
                    "structure": base.get("structure"),
                    "traditional": base.get("traditional"),
                    "variant": base.get("variant"),
                    "synonyms": related.get("synonyms"),
                    "antonyms": related.get("antonyms"),
                    "likeness": related.get("likeness"),
                }.items()
                if v
            }
            writer.writerow(
                _empty_row(
                    word=char,
                    phonetic="/".join(pinyin_list),
                    translation=format_char_translation(entry),
                    detail=detail or None,
                )
            )
            count += 1
    return count


def build_word_dictionary(source: Path, out_path: Path) -> int:
    word_path = source / "word" / "word.json"
    idiom_path = source / "idiom" / "idiom.json"

    idiom_by_word: dict[str, dict[str, Any]] = {
        item["word"]: item for item in load_json_array(idiom_path)
    }

    count = 0
    with out_path.open("w", encoding="utf-8", newline="") as out_f, word_path.open(
        "r", encoding="utf-8"
    ) as in_f:
        writer = csv.DictWriter(out_f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for entry in json.load(in_f):
            word = entry.get("word")
            if not word:
                continue
            idiom = idiom_by_word.get(word)
            detail = {"abbr": entry.get("abbr")} if entry.get("abbr") else {}
            if idiom:
                for key in (
                    "source",
                    "quote",
                    "story",
                    "similar",
                    "opposite",
                    "usage",
                    "notice",
                    "spelling",
                ):
                    value = idiom.get(key)
                    if value:
                        detail[key] = value
            writer.writerow(
                _empty_row(
                    word=word,
                    phonetic=entry.get("pinyin", ""),
                    translation=entry.get("explanation", ""),
                    detail=detail or None,
                )
            )
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="chinese-dictionary 仓库根目录")
    parser.add_argument("--out-dir", default="./out", help="CSV 输出目录")
    args = parser.parse_args()

    source = Path(args.source)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    char_out = out_dir / "汉语字典.csv"
    word_out = out_dir / "汉语词典.csv"

    print(f"转换汉语字典 -> {char_out}")
    char_count = build_char_dictionary(source, char_out)
    print(f"  完成，{char_count} 条")

    print(f"转换汉语词典 -> {word_out}")
    word_count = build_word_dictionary(source, word_out)
    print(f"  完成，{word_count} 条")


if __name__ == "__main__":
    sys.exit(main())
