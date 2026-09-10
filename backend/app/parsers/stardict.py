import gzip
import struct
from collections.abc import Iterator
from pathlib import Path

from app.parsers.base import DictionaryParser, ParsedEntry

_TEXT_TYPES = {"m", "l", "t", "y", "g", "x"}  # 纯文本/语法/词源等，按文本展示
_HTML_TYPES = {"h"}


def _parse_ifo(ifo_path: Path) -> dict[str, str]:
    meta: dict[str, str] = {}
    with ifo_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("StarDict") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            meta[key.strip()] = value.strip()
    return meta


def _read_dict_content(dict_path: Path) -> bytes:
    if dict_path.suffix == ".dz" or dict_path.name.endswith(".dict.dz"):
        with gzip.open(dict_path, "rb") as f:
            return f.read()
    return dict_path.read_bytes()


def _iter_idx_entries(idx_bytes: bytes, offset_bits: int) -> Iterator[tuple[str, int, int]]:
    offset_size = 8 if offset_bits == 64 else 4
    pos = 0
    length = len(idx_bytes)
    while pos < length:
        end = idx_bytes.index(b"\x00", pos)
        word = idx_bytes[pos:end].decode("utf-8", errors="replace")
        pos = end + 1
        offset = int.from_bytes(idx_bytes[pos : pos + offset_size], "big")
        pos += offset_size
        entry_len = int.from_bytes(idx_bytes[pos : pos + 4], "big")
        pos += 4
        yield word, offset, entry_len


def _iter_syn_entries(syn_bytes: bytes) -> Iterator[tuple[str, int]]:
    pos = 0
    length = len(syn_bytes)
    while pos < length:
        end = syn_bytes.index(b"\x00", pos)
        word = syn_bytes[pos:end].decode("utf-8", errors="replace")
        pos = end + 1
        (word_index,) = struct.unpack_from(">I", syn_bytes, pos)
        pos += 4
        yield word, word_index


def _render_content(raw: bytes, sametypesequence: str | None) -> str:
    """按 sametypesequence 指示的类型解释内容；未指定时按纯文本兜底（简化实现）。"""
    if not sametypesequence:
        return raw.decode("utf-8", errors="replace")
    # 常见词典只使用单一类型；多类型顺序拼接的场景本期不做分段展示，取全部文本内容。
    return raw.decode("utf-8", errors="replace")


class StarDictParser(DictionaryParser):
    def parse(
        self,
        file_paths: list[Path],
        *,
        dictionary_id: int,
        resource_dir: Path,
    ) -> Iterator[ParsedEntry]:
        by_suffix: dict[str, Path] = {}
        for path in file_paths:
            name = path.name.lower()
            if name.endswith(".dict.dz"):
                by_suffix["dict"] = path
            elif name.endswith(".idx.gz"):
                by_suffix["idx_gz"] = path
            else:
                by_suffix[path.suffix.lstrip(".").lower()] = path

        ifo_path = by_suffix.get("ifo")
        idx_path = by_suffix.get("idx") or by_suffix.get("idx_gz")
        dict_path = by_suffix.get("dict")
        syn_path = by_suffix.get("syn")
        if ifo_path is None or idx_path is None or dict_path is None:
            raise ValueError("StarDict 词典缺少必要的 .ifo/.idx/.dict 文件")

        meta = _parse_ifo(ifo_path)
        offset_bits = int(meta.get("idxoffsetbits", "32"))
        sametypesequence = meta.get("sametypesequence")

        idx_bytes = (
            gzip.open(idx_path, "rb").read() if idx_path.suffix == ".gz" else idx_path.read_bytes()
        )
        dict_bytes = _read_dict_content(dict_path)

        entries = list(_iter_idx_entries(idx_bytes, offset_bits))
        word_by_index = {i: word for i, (word, _, _) in enumerate(entries)}

        for word, offset, length in entries:
            raw = dict_bytes[offset : offset + length]
            definition = _render_content(raw, sametypesequence)
            yield ParsedEntry(word=word, definition=definition)

        if syn_path is not None:
            syn_bytes = syn_path.read_bytes()
            for alias, word_index in _iter_syn_entries(syn_bytes):
                target_word = word_by_index.get(word_index)
                if target_word is None:
                    continue
                word, offset, length = entries[word_index]
                raw = dict_bytes[offset : offset + length]
                definition = _render_content(raw, sametypesequence)
                yield ParsedEntry(
                    word=alias, definition=definition, extra={"alias_of": target_word}
                )
