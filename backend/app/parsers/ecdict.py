import csv
import json
from collections.abc import Iterator
from pathlib import Path

from app.parsers.base import (
    SAMPLE_SCAN_FACTOR,
    DictionaryParser,
    ParsedEntry,
    is_informative,
    is_informative_headword,
    spread_downsample,
)

_EXTRA_INT_FIELDS = ("collins", "oxford", "bnc", "frq")
_EXTRA_STR_FIELDS = ("pos", "tag", "exchange", "audio")


def _to_int(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def _build_extra(row: dict[str, str]) -> dict | None:
    extra: dict = {}
    for field in _EXTRA_INT_FIELDS:
        value = (row.get(field) or "").strip()
        if value:
            extra[field] = _to_int(value)
    for field in _EXTRA_STR_FIELDS:
        value = (row.get(field) or "").strip()
        if value:
            extra[field] = value

    # detail 列若为合法 JSON，透传合并进 extra，用于承载
    # collins/oxford/tag/bnc/frq/exchange 之外更丰富的结构化数据（如中文语料）。
    detail_raw = (row.get("detail") or "").strip()
    if detail_raw:
        try:
            detail = json.loads(detail_raw)
        except (ValueError, TypeError):
            detail = None
        if isinstance(detail, dict):
            extra.update(detail)

    return extra or None


class EcdictParser(DictionaryParser):
    def parse(
        self,
        file_paths: list[Path],
        *,
        dictionary_id: int,
        resource_dir: Path | None,
    ) -> Iterator[ParsedEntry]:
        csv_path = file_paths[0]
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                word = (row.get("word") or "").strip()
                if not word:
                    continue
                # ECDICT 源 CSV 里同一单元格的多行释义用字面 "\n"（反斜杠+n）分隔，
                # 不是真正的换行符（CSV 字段本身避免嵌入真实换行），这里转成真换行，
                # 前端 white-space: pre-wrap 才能正确断行，而不是显示出字面的 \n。
                definition_en = (row.get("definition") or "").strip().replace("\\n", "\n")
                translation_zh = (row.get("translation") or "").strip().replace("\\n", "\n")
                combined = "\n\n".join(part for part in (definition_en, translation_zh) if part)
                yield ParsedEntry(
                    word=word,
                    definition=combined,
                    phonetic=(row.get("phonetic") or "").strip() or None,
                    extra=_build_extra(row),
                )

    def sample(self, file_paths: list[Path], limit: int) -> list[ParsedEntry]:
        """读到够 limit 条「有信息量」的词条；采样不需要 phonetic/extra，
        省掉 _build_extra 的 JSON 解析。"""
        sampled: list[ParsedEntry] = []
        scanned = 0
        scan_cap = limit * SAMPLE_SCAN_FACTOR
        with file_paths[0].open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                scanned += 1
                if scanned > scan_cap:
                    break
                word = (row.get("word") or "").strip()
                if not word:
                    continue
                definition_en = (row.get("definition") or "").strip()
                translation_zh = (row.get("translation") or "").strip()
                combined = "\n\n".join(part for part in (definition_en, translation_zh) if part)
                if not is_informative(word, combined):
                    continue
                sampled.append(ParsedEntry(word=word, definition=combined))
                if len(sampled) >= limit:
                    break
        return sampled

    def sample_headwords(self, file_paths: list[Path], limit: int) -> list[str]:
        """按字节偏移在 CSV 中跨整份取样。

        ECDICT 是英文词典，开头并不会像扫描版词典那样全是索引项，但「取中段」让采样
        对任何来源的 CSV 都成立，也让这个接口与前两种格式行为一致。
        """
        csv_path = file_paths[0]
        size = csv_path.stat().st_size
        if size <= 0:
            return []
        words: list[str] = []
        with csv_path.open("rb") as fb:
            header = next(csv.reader([fb.readline().decode("utf-8-sig", errors="replace")]), [])
            try:
                word_index = header.index("word")
            except ValueError:
                word_index = 0
            # 取样点数按 2 倍目标取，并且**探完整段**再统一下采样——中途收满就停会退回
            # 「只取开头」，那正是要修的问题
            probes = limit * 2
            for k in range(probes):
                target = min(size - 1, size * k // probes)
                fb.seek(target)
                fb.readline()  # 丢弃被 seek 截断的半行
                line = fb.readline()
                if not line:
                    continue
                for row in csv.reader([line.decode("utf-8", errors="replace")]):
                    if len(row) <= word_index:
                        continue
                    word = row[word_index].strip()
                    if is_informative_headword(word):
                        words.append(word)
        return spread_downsample(words, limit)
