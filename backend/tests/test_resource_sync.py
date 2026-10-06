"""启动时自动补齐附属资源的用例。

背景：附属资源的扩展名白名单会随上游修复增补（最近一次是 `.ini`——词典用
`<script src="config.ini">` 加载 JS 配置，缺了它词典自带脚本会把整页板块隐藏），
但白名单只对**新导入**的词典生效，已导入词典的 res/ 不会自己更新。启动时补缺这一步
就是为了关掉这个窗口，它的行为必须满足：补缺、不覆盖、跳过非白名单、可重复跑。
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.dictionary import Dictionary
from app.services.dictionary_service import sync_sibling_resources


def _make_dictionary(db: Session, source_dir: Path, name: str = "附属资源测试词典") -> Dictionary:
    dictionary = Dictionary(
        name=name,
        format="mdict",
        lang_from="en",
        lang_to="en",
        file_path=str(source_dir / "test.mdx"),
        status="enabled",
    )
    db.add(dictionary)
    db.commit()
    return dictionary


def test_sync_sibling_resources_copies_missing_only(db_session: Session, tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "test.mdx").write_bytes(b"MDX")  # 词典本体：不在白名单里，绝不复制
    (source / "config.ini").write_bytes(b"header = 1;")  # 该补的（.ini 依赖）
    (source / "old.css").write_bytes(b"new")  # res/ 里已有一份，不覆盖
    (source / "说明.pdf").write_bytes(b"%PDF")  # 非白名单（Eudic 索引/PDF 刻意排除）
    dictionary = _make_dictionary(db_session, source)

    res = Path(get_settings().dictionary_storage_path) / str(dictionary.id) / "res"
    res.mkdir(parents=True)
    (res / "old.css").write_bytes(b"old")

    fixed, copied = sync_sibling_resources(db_session, get_settings())
    assert copied >= 1 and fixed >= 1  # 同一测试库里可能有别的词典，只看「至少补了这部」
    assert (res / "config.ini").read_bytes() == b"header = 1;"
    assert (res / "old.css").read_bytes() == b"old"
    assert not (res / "说明.pdf").exists()
    assert not (res / "test.mdx").exists()
    assert [p.name for p in res.iterdir() if p.name.startswith("config.ini.tmp")] == []

    # 幂等：再跑一次没有东西可补
    assert sync_sibling_resources(db_session, get_settings()) == (0, 0)


def test_sync_sibling_resources_ignores_missing_source_dir(
    db_session: Session, tmp_path: Path
) -> None:
    """源目录被删/不可达时只跳过这部词典，不能抛出去打断其余词典与启动。"""
    gone = tmp_path / "gone"
    dictionary = _make_dictionary(db_session, gone, name="源目录已消失")

    res = Path(get_settings().dictionary_storage_path) / str(dictionary.id) / "res"
    sync_sibling_resources(db_session, get_settings())  # 不抛异常即通过
    assert not res.exists()
