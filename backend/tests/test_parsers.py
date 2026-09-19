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


def test_ecdict_parser_converts_literal_newlines(tmp_path: Path) -> None:
    """ECDICT 源 CSV 里同一单元格多行释义用字面 "\\n" 分隔，不是真换行，解析时应转换，
    否则页面上会直接显示出 \\n 这两个字符而不是换行。"""
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
    rows = [
        {
            "word": "people",
            "phonetic": "",
            "definition": "n. group of humans\\nv. fill with people",
            "translation": "n. 人民\\nvt. 居住于",
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

    definition = results[0].definition
    assert "\\n" not in definition
    assert "n. group of humans\nv. fill with people" in definition
    assert "n. 人民\nvt. 居住于" in definition


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


def _snapshot(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*")}


def test_stardict_sample_reads_only_prefix_and_writes_nothing(tmp_path: Path) -> None:
    paths = _build_stardict(tmp_path)
    before = _snapshot(tmp_path)

    sampled = StarDictParser().sample(paths, limit=1)

    assert [entry.word for entry in sampled] == ["apple"]
    assert sampled[0].definition == "n. 苹果"
    # 采样是只读的：不该落盘任何东西（.syn 别名条目也不在采样范围内）
    assert _snapshot(tmp_path) == before


def test_ecdict_sample_reads_at_most_limit_rows(tmp_path: Path) -> None:
    import csv

    csv_path = tmp_path / "ecdict.csv"
    fieldnames = ["word", "definition", "translation"]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            [
                {"word": "apple", "definition": "a fruit", "translation": "苹果"},
                {"word": "banana", "definition": "a fruit", "translation": "香蕉"},
                {"word": "cherry", "definition": "a fruit", "translation": "樱桃"},
            ]
        )

    sampled = EcdictParser().sample([csv_path], limit=2)

    assert [entry.word for entry in sampled] == ["apple", "banana"]
    assert sampled[0].definition == "a fruit\n\n苹果"


def test_mdict_parse_without_resource_dir_skips_extraction(tmp_path: Path) -> None:
    """resource_dir=None 表示「只要释义、不要发音/图片」。

    此时既不解包 .mdd，也不改写释义里的资源引用——改成 /dict-res/... 只会指向不存在的
    文件，保留原始相对引用更诚实。
    """
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
    writer.pack(
        str(mdx_path),
        writer.pack_mdx_txt(str(txt_path), encoding="utf-8"),
        title="Test",
        description="",
        encoding="utf-8",
    )
    mdd_path = tmp_path / "test.mdd"
    writer.pack(
        str(mdd_path),
        writer.pack_mdd_file(str(res_dir)),
        title="Test",
        description="",
        is_mdd=True,
    )

    before = _snapshot(tmp_path)
    results = list(MDictParser().parse([mdx_path, mdd_path], dictionary_id=42, resource_dir=None))

    by_word = {entry.word: entry for entry in results}
    assert "yellow fruit" in by_word["banana"].definition
    assert 'src="pic/apple.png"' in by_word["apple"].definition
    assert "/dict-res/" not in by_word["apple"].definition
    # 与解析前逐文件对比：没有解包出任何资源
    assert _snapshot(tmp_path) == before


def test_mdict_lzo_error_becomes_readable_validation_error(tmp_path: Path, monkeypatch) -> None:
    """缺 LZO 支持时要给出可读原因，而不是裸抛 RuntimeError。

    裸抛会被后台任务的兜底分支变成「服务器内部错误，请查看后端日志」，管理员看不出是格式问题
    （真实遇到过：MDict 引擎版本 1.2 的老词典用 LZO 压缩块，而 mdict-utils 的可选依赖
    python-lzo 没装）。
    """

    class LzoMDX:
        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError("LZO compression is not supported")

    monkeypatch.setattr("app.parsers.mdict.MDX", LzoMDX)
    parser = MDictParser()
    try:
        list(parser.parse([tmp_path / "legacy.mdx"], dictionary_id=1, resource_dir=None))
    except ValueError as exc:
        assert "legacy.mdx" in str(exc)
        assert "LZO" in str(exc)
    else:
        raise AssertionError("expected ValueError for LZO-compressed dictionary")

    # 其它 RuntimeError 不能被一起吞掉，否则会把真实故障误报成「格式不支持」
    class BrokenMDX:
        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError("something else broke")

    monkeypatch.setattr("app.parsers.mdict.MDX", BrokenMDX)
    try:
        list(parser.parse([tmp_path / "broken.mdx"], dictionary_id=1, resource_dir=None))
    except ValueError:
        raise AssertionError("只应转译 LZO 这一种情况，其它 RuntimeError 需原样抛出") from None
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError to propagate")


def test_mdict_sample_does_not_extract_mdd_resources(tmp_path: Path) -> None:
    """采样的回归保护：绝不能走 parse()。

    parse() 会把 .mdd 里的图片/音频全量落盘，采样只是为了判断语言，不该有这个副作用，
    释义也应保持原始 HTML 而非被改写成 /dict-res/... 绝对路径。
    """
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
    writer.pack(
        str(mdx_path),
        writer.pack_mdx_txt(str(txt_path), encoding="utf-8"),
        title="Test",
        description="",
        encoding="utf-8",
    )
    mdd_path = tmp_path / "test.mdd"
    writer.pack(
        str(mdd_path),
        writer.pack_mdd_file(str(res_dir)),
        title="Test",
        description="",
        is_mdd=True,
    )

    before = _snapshot(tmp_path)
    sampled = MDictParser().sample([mdx_path, mdd_path], limit=10)

    assert {entry.word for entry in sampled} == {"apple", "banana"}
    assert _snapshot(tmp_path) == before
    apple = next(entry for entry in sampled if entry.word == "apple")
    assert 'src="pic/apple.png"' in apple.definition
    assert "/dict-res/" not in apple.definition
