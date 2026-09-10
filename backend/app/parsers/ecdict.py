import csv
import json
from collections.abc import Iterator
from pathlib import Path

from app.parsers.base import DictionaryParser, ParsedEntry

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
        resource_dir: Path,
    ) -> Iterator[ParsedEntry]:
        csv_path = file_paths[0]
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                word = (row.get("word") or "").strip()
                if not word:
                    continue
                definition_en = (row.get("definition") or "").strip()
                translation_zh = (row.get("translation") or "").strip()
                combined = "\n\n".join(part for part in (definition_en, translation_zh) if part)
                yield ParsedEntry(
                    word=word,
                    definition=combined,
                    phonetic=(row.get("phonetic") or "").strip() or None,
                    extra=_build_extra(row),
                )
