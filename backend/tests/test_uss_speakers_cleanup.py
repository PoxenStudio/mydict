"""牛津9 红色美音例句喇叭清理（remove_missing_uss_speakers）的用例。

美音 mp3 源词典就基本没打包（实测 38,869 个引用里 99% 缺失），这里验证：只删
「指向缺失文件」的红色喇叭锚点，文件还在的按钮、蓝色英音喇叭与例句文本都保留。
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.services.definition_repair import remove_missing_uss_speakers
from tests.test_definition_repair import _add_entry, _definition, _make_dictionary


def _uss_anchor(dictionary_id: int, name: str) -> str:
    return (
        f'<a href="/dict-res/{dictionary_id}/res/{name}">'
        "<audio-uss-liju>\U0001F50A</audio-uss-liju></a>"
    )


def test_remove_missing_uss_speakers(db_session: Session, tmp_path: Path) -> None:
    dictionary = _make_dictionary(db_session, "美音喇叭测试")
    did = dictionary.id
    res_dir = tmp_path / "res"
    res_dir.mkdir()
    (res_dir / "exists_uss_1.mp3").write_bytes(b"ID3")

    ok = _uss_anchor(did, "exists_uss_1.mp3")
    missing = _uss_anchor(did, "missing_uss_1.mp3")
    gbs = (
        f'<a href="/dict-res/{did}/res/gbs_1.mp3">'
        "<audio-gbs-liju>\U0001F50A</audio-gbs-liju></a>"
    )
    pair = f"<x-wr>例句。<audio-wr>{gbs}{missing}</audio-wr></x-wr>"

    kept = _add_entry(db_session, did, "kept", f"有文件：{ok}")
    removed = _add_entry(db_session, did, "removed", pair)
    plain = _add_entry(db_session, did, "plain", "<p>没有喇叭的词条</p>")

    entries, speakers = remove_missing_uss_speakers(db_session, did, res_dir)

    assert (entries, speakers) == (1, 1)
    assert "audio-uss-liju" not in _definition(db_session, removed.id)
    # 蓝色英音喇叭与例句文本原样保留
    assert "audio-gbs-liju" in _definition(db_session, removed.id)
    assert "例句。" in _definition(db_session, removed.id)
    # 文件还在的红色喇叭保留
    assert ok in _definition(db_session, kept.id)
    assert _definition(db_session, plain.id) == "<p>没有喇叭的词条</p>"
    # 幂等：再跑一遍改动为 0
    assert remove_missing_uss_speakers(db_session, did, res_dir) == (0, 0)
