import json
import struct
from pathlib import Path

from app.parsers.ecdict import EcdictParser
from app.parsers.mdict import MDictParser
from app.parsers.stardict import StarDictParser


def _build_stardict(
    tmp_path: Path, *, sametypesequence: str = "m", with_syn: bool = True
) -> list[Path]:
    entries = [("apple", "n. 苹果"), ("banana", "n. 香蕉")]
    dict_bytes = b""
    idx_bytes = b""
    offsets = []
    for word, definition in entries:
        content = definition.encode("utf-8")
        offsets.append((word, len(dict_bytes), len(content)))
        dict_bytes += content
    for word, offset, length in offsets:
        idx_bytes += word.encode("utf-8") + b"\x00"
        idx_bytes += struct.pack(">I", offset)
        idx_bytes += struct.pack(">I", length)

    ifo_path = tmp_path / "test.ifo"
    ifo_path.write_text(
        "StarDict's dict ifo file\n"
        "version=2.4.2\n"
        "bookname=Test Dict\n"
        f"wordcount={len(entries)}\n"
        f"idxfilesize={len(idx_bytes)}\n"
        f"sametypesequence={sametypesequence}\n",
        encoding="utf-8",
    )
    idx_path = tmp_path / "test.idx"
    idx_path.write_bytes(idx_bytes)
    dict_path = tmp_path / "test.dict"
    dict_path.write_bytes(dict_bytes)

    paths = [ifo_path, idx_path, dict_path]
    if with_syn:
        syn_bytes = "apl".encode("utf-8") + b"\x00" + struct.pack(">I", 0)
        syn_path = tmp_path / "test.syn"
        syn_path.write_bytes(syn_bytes)
        paths.append(syn_path)
    return paths


def test_stardict_parser_basic(tmp_path: Path) -> None:
    paths = _build_stardict(tmp_path)
    parser = StarDictParser()
    results = list(parser.parse(paths, dictionary_id=1, resource_dir=tmp_path / "res"))

    by_word = {e.word: e for e in results}
    assert by_word["apple"].definition == "n. 苹果"
    assert by_word["banana"].definition == "n. 香蕉"
    # .syn 别名条目应指向主词条内容
    assert by_word["apl"].definition == "n. 苹果"
    assert by_word["apl"].extra == {"alias_of": "apple"}


def test_stardict_parser_missing_files_raises(tmp_path: Path) -> None:
    parser = StarDictParser()
    try:
        list(parser.parse([tmp_path / "only.ifo"], dictionary_id=1, resource_dir=tmp_path))
    except ValueError:
        return
    raise AssertionError("expected ValueError for incomplete StarDict file set")


def test_ecdict_parser_basic(tmp_path: Path) -> None:
    import csv

    csv_path = tmp_path / "ecdict.csv"
    fieldnames = [
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
    detail_json = json.dumps({"strokes": 4, "radicals": "木"}, ensure_ascii=False)
    rows = [
        {
            "word": "apple",
            "phonetic": "æpl",
            "definition": "n. a fruit",
            "translation": "苹果",
            "pos": "n",
            "collins": "3",
            "oxford": "1",
            "tag": "zk gk",
            "bnc": "100",
            "frq": "200",
            "exchange": "",
            "detail": detail_json,
            "audio": "",
        },
        {
            "word": "banana",
            "phonetic": "",
            "definition": "",
            "translation": "香蕉",
            "pos": "",
            "collins": "",
            "oxford": "",
            "tag": "",
            "bnc": "",
            "frq": "",
            "exchange": "",
            "detail": "",
            "audio": "",
        },
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    parser = EcdictParser()
    results = list(parser.parse([csv_path], dictionary_id=1, resource_dir=tmp_path))

    by_word = {e.word: e for e in results}
    apple = by_word["apple"]
    assert apple.phonetic == "æpl"
    assert "a fruit" in apple.definition
    assert "苹果" in apple.definition
    assert apple.extra["collins"] == 3
    assert apple.extra["oxford"] == 1
    assert apple.extra["tag"] == "zk gk"
    # detail JSON 透传合并进 extra
    assert apple.extra["strokes"] == 4
    assert apple.extra["radicals"] == "木"

    banana = by_word["banana"]
    assert banana.definition == "香蕉"
    assert banana.extra is None


def test_mdict_parser_with_resources(tmp_path: Path) -> None:
    from mdict_utils import writer

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    txt_path = src_dir / "words.txt"
    txt_path.write_text(
        'apple\n<p>a fruit <img src="pic/apple.png"></p>\n</>\n'
        "banana\n<p>yellow fruit</p>\n</>\n",
        encoding="utf-8",
    )

    res_dir = tmp_path / "mdd_src"
    (res_dir / "pic").mkdir(parents=True)
    (res_dir / "pic" / "apple.png").write_bytes(b"\x89PNG-fake-content")

    mdx_path = tmp_path / "test.mdx"
    mdx_dict = writer.pack_mdx_txt(str(txt_path), encoding="utf-8")
    writer.pack(str(mdx_path), mdx_dict, title="Test", description="", encoding="utf-8")

    mdd_path = tmp_path / "test.mdd"
    mdd_dict = writer.pack_mdd_file(str(res_dir))
    writer.pack(str(mdd_path), mdd_dict, title="Test", description="", is_mdd=True)

    resource_dir = tmp_path / "resources"
    parser = MDictParser()
    results = list(parser.parse([mdx_path, mdd_path], dictionary_id=42, resource_dir=resource_dir))

    by_word = {e.word: e for e in results}
    assert "yellow fruit" in by_word["banana"].definition
    assert "/dict-res/42/res/pic/apple.png" in by_word["apple"].definition
    assert (resource_dir / "pic" / "apple.png").read_bytes() == b"\x89PNG-fake-content"
