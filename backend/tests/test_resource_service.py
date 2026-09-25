import tempfile
from pathlib import Path

import pytest

from app.services.resource_service import (
    copy_sibling_resources,
    normalize_resource_path,
    resolve_resource_file,
    rewrite_resource_refs,
    strip_legacy_file_prefix,
    write_resource,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("pic/apple.png", "pic/apple.png"),
        ("/pic/apple.png", "pic/apple.png"),
        ("\\pic\\apple.png", "pic/apple.png"),
        ("./pic/apple.png", "pic/apple.png"),
    ],
)
def test_normalize_resource_path_ok(raw: str, expected: str) -> None:
    assert normalize_resource_path(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "../etc/passwd",
        "pic/../../etc/passwd",
        "..\\..\\windows\\system32",
        "a/b/../../../c",
    ],
)
def test_normalize_resource_path_rejects_traversal(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_resource_path(raw)


def test_write_resource_creates_nested_dirs(tmp_path: Path) -> None:
    write_resource(tmp_path, "pic/sub/apple.png", b"content")
    target = tmp_path / "pic" / "sub" / "apple.png"
    assert target.read_bytes() == b"content"


def test_write_resource_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_resource(tmp_path, "../../etc/passwd", b"evil")


def test_write_resource_without_overwrite_keeps_existing_and_adds_missing(tmp_path: Path) -> None:
    """重新解析给正在服务的词典补资源：已有文件不动，缺的补上，不留临时文件。"""
    write_resource(tmp_path, "a/x.png", b"old")
    write_resource(tmp_path, "a/x.png", b"new", overwrite=False)
    write_resource(tmp_path, "a/y.png", b"added", overwrite=False)
    assert (tmp_path / "a" / "x.png").read_bytes() == b"old"
    assert (tmp_path / "a" / "y.png").read_bytes() == b"added"
    assert sorted(p.name for p in (tmp_path / "a").iterdir()) == ["x.png", "y.png"]


# ------------------------------------------------------- MDict 同级附属资源
#
# MDict 的样式表/字体/脚本放在 .mdx 同级目录而不是 .mdd 里，词条的 <link href="oxbw.css">
# 就指着它们。早先只解包 .mdd，于是这些文件全部 404——图标按原始像素渲染、表格丢边框。


def test_copy_sibling_resources_copies_web_resources(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "oxbw.css").write_bytes(b"img.audio{height:1em}")
    (source / "oxbw.js").write_bytes(b"void 0")
    (source / "font.otf").write_bytes(b"OTTO")
    (source / "cover.png").write_bytes(b"\x89PNG")
    mdx = source / "dict.mdx"
    mdx.write_bytes(b"mdx-body")

    resource_dir = tmp_path / "res"
    assert copy_sibling_resources(resource_dir, [mdx]) == 4

    assert (resource_dir / "oxbw.css").read_bytes() == b"img.audio{height:1em}"
    assert (resource_dir / "oxbw.js").exists()
    assert (resource_dir / "font.otf").exists()
    assert (resource_dir / "cover.png").exists()


def test_copy_sibling_resources_skips_dictionary_files(tmp_path: Path) -> None:
    """词典本体不进 res/：词条已入库、.mdd 已解包，复制本体只会白占几十 MB。"""
    source = tmp_path / "src"
    source.mkdir()
    mdx = source / "dict.mdx"
    mdx.write_bytes(b"mdx-body")
    (source / "dict.mdd").write_bytes(b"mdd-body")
    (source / "style.css").write_bytes(b"x")

    resource_dir = tmp_path / "res"
    copy_sibling_resources(resource_dir, [mdx])

    assert not (resource_dir / "dict.mdx").exists()
    assert not (resource_dir / "dict.mdd").exists()


def test_copy_sibling_resources_skips_non_web_extensions(tmp_path: Path) -> None:
    """Eudic 专有索引（.db/.bix/.bin）与说明书（.pdf）与渲染无关，实测占附属文件大小的
    六成，不能跟着复制。"""
    source = tmp_path / "src"
    source.mkdir()
    mdx = source / "dict.mdx"
    mdx.write_bytes(b"mdx")
    for name in ("index.db", "index.db-wal", "combined.bin", "concise.bix", "readme.pdf"):
        (source / name).write_bytes(b"junk")
    (source / "style.css").write_bytes(b"x")

    resource_dir = tmp_path / "res"
    assert copy_sibling_resources(resource_dir, [mdx]) == 1
    assert (resource_dir / "style.css").exists()
    assert sorted(p.name for p in resource_dir.iterdir()) == ["style.css"]


def test_copy_sibling_resources_keeps_existing_file(tmp_path: Path) -> None:
    """同名文件已存在时不覆盖：那份是 .mdd 里解包出来的，属于词典容器内，更权威。"""
    source = tmp_path / "src"
    source.mkdir()
    mdx = source / "dict.mdx"
    mdx.write_bytes(b"mdx")
    (source / "style.css").write_bytes(b"from-sibling")

    resource_dir = tmp_path / "res"
    resource_dir.mkdir()
    (resource_dir / "style.css").write_bytes(b"from-mdd")

    assert copy_sibling_resources(resource_dir, [mdx]) == 0
    assert (resource_dir / "style.css").read_bytes() == b"from-mdd"


def test_copy_sibling_resources_accepts_directory_source(tmp_path: Path) -> None:
    """浏览器上传导入的 file_path 存的是该词典的 source/ 目录，不是文件列表。"""
    source = tmp_path / "source"
    source.mkdir()
    (source / "style.css").write_bytes(b"x")

    resource_dir = tmp_path / "res"
    assert copy_sibling_resources(resource_dir, [source]) == 1
    assert (resource_dir / "style.css").exists()


def test_copy_sibling_resources_tolerates_missing_source(tmp_path: Path) -> None:
    """源词典被挪走/卸载时只记 warning，不能让补齐任务整体失败。"""
    resource_dir = tmp_path / "res"
    assert copy_sibling_resources(resource_dir, [tmp_path / "gone" / "dict.mdx"]) == 0


def test_copy_sibling_resources_leaves_no_temp_files(tmp_path: Path) -> None:
    """写入是「临时文件 + os.replace」的原子替换，不能留下半截产物。"""
    source = tmp_path / "src"
    source.mkdir()
    mdx = source / "dict.mdx"
    mdx.write_bytes(b"mdx")
    (source / "style.css").write_bytes(b"x")

    resource_dir = tmp_path / "res"
    copy_sibling_resources(resource_dir, [mdx])

    assert sorted(p.name for p in resource_dir.iterdir()) == ["style.css"]


def test_copy_sibling_resources_ignores_directories(tmp_path: Path) -> None:
    """只扫一层直接子文件：实测资源都在词典目录这一层，子目录不当资源复制。"""
    source = tmp_path / "src"
    source.mkdir()
    mdx = source / "dict.mdx"
    mdx.write_bytes(b"mdx")
    nested = source / "images"
    nested.mkdir()
    (nested / "inner.css").write_bytes(b"x")

    resource_dir = tmp_path / "res"
    assert copy_sibling_resources(resource_dir, [mdx]) == 0


# ------------------------------------------------- 资源请求的路径解析
#
# 词典多在 Windows 上打包，词条引用与 .mdd 里的键大小写常常不一致（实测汉典的图片引用
# 全部是小写、实际键是混合大小写；新漢語林2 正好相反）。Windows 与 MDict 客户端都不区分
# 大小写，Linux 上直接 404——表现为词条里的文字图片整片丢失。


def test_strip_legacy_file_prefix() -> None:
    # 早期改写把 file:///down/x.gif 拼成了 res/file:/down/x.gif
    assert strip_legacy_file_prefix("file:/down/x.gif") == "down/x.gif"
    assert strip_legacy_file_prefix("FILE:/down/x.gif") == "down/x.gif"
    # 正常路径不受影响
    assert strip_legacy_file_prefix("down/x.gif") == "down/x.gif"
    # 只在开头剥，路径中间出现 file: 字样不动
    assert strip_legacy_file_prefix("a/file:/b.gif") == "a/file:/b.gif"


def test_resolve_resource_file_exact_hit(tmp_path: Path) -> None:
    (tmp_path / "down" / "7").mkdir(parents=True)
    target = tmp_path / "down" / "7" / "x.gif"
    target.write_bytes(b"gif")
    assert resolve_resource_file(tmp_path, "down/7/x.gif") == target



def _filesystem_is_case_sensitive() -> bool:
    with tempfile.TemporaryDirectory() as directory:
        Path(directory, "probe").touch()
        return not Path(directory, "PROBE").exists()


# 大小写不敏感的文件系统（macOS 默认的 APFS）上精确匹配会直接命中，返回的是引用里的写法
# 而不是磁盘上的真实文件名，这几条断言没有意义；生产环境（Linux 容器）照常跑
case_sensitive_fs_only = pytest.mark.skipif(
    not _filesystem_is_case_sensitive(), reason="文件系统不区分大小写"
)


@case_sensitive_fs_only
def test_resolve_resource_file_matches_case_insensitively(tmp_path: Path) -> None:
    """汉典的真实形态：引用全小写、实际键是混合大小写。"""
    (tmp_path / "down" / "30").mkdir(parents=True)
    real = tmp_path / "down" / "30" / "305626w1b7F8B.gif"
    real.write_bytes(b"gif")

    assert resolve_resource_file(tmp_path, "down/30/305626w1b7f8b.gif") == real


@case_sensitive_fs_only
def test_resolve_resource_file_matches_uppercase_reference(tmp_path: Path) -> None:
    """新漢語林2 的真实形态：引用是大写、实际文件是小写。"""
    (tmp_path / "gaiji").mkdir()
    real = tmp_path / "gaiji" / "b245.png"
    real.write_bytes(b"png")

    assert resolve_resource_file(tmp_path, "gaiji/B245.png") == real


@case_sensitive_fs_only
def test_resolve_resource_file_matches_directory_component(tmp_path: Path) -> None:
    (tmp_path / "gaiji").mkdir()
    real = tmp_path / "gaiji" / "b245.png"
    real.write_bytes(b"png")

    assert resolve_resource_file(tmp_path, "Gaiji/B245.png") == real


def test_resolve_resource_file_missing_returns_none(tmp_path: Path) -> None:
    (tmp_path / "down").mkdir()
    assert resolve_resource_file(tmp_path, "down/nope.gif") is None
    assert resolve_resource_file(tmp_path, "") is None
    # 中间目录不存在也不能抛异常
    assert resolve_resource_file(tmp_path, "nodir/nope.gif") is None


def test_resolve_resource_file_does_not_escape_root(tmp_path: Path) -> None:
    """兜底查找只能在 res/ 里挑名字，不能顺着 .. 走出去。"""
    outside = tmp_path.parent / "outside-secret.png"
    outside.write_bytes(b"secret")
    res_dir = tmp_path / "res"
    res_dir.mkdir()

    # normalize_resource_path 已经拒了这类路径，这里再确认兜底逻辑自己也不会越界
    assert resolve_resource_file(res_dir, "../outside-secret.png") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 词典内部资源：改写成可访问的绝对 URL
        ("pic/apple.png", "/dict-res/7/res/pic/apple.png"),
        ("snd/apple.mp3", "/dict-res/7/res/snd/apple.mp3"),
        ("\\pic\\apple.png", "/dict-res/7/res/pic/apple.png"),
        ("/pic/apple.png", "/dict-res/7/res/pic/apple.png"),
        # sound:// 音频协议：转成可播放 URL（.spx 浏览器不支持，前端再决定怎么处理）
        ("sound://audio/apple.spx", "/dict-res/7/res/audio/apple.spx"),
        ("sound://a/b/c.mp3", "/dict-res/7/res/a/b/c.mp3"),
        ("SOUND://audio/x.wav", "/dict-res/7/res/audio/x.wav"),
        # 查询串与锚点要保留，不能当成路径的一部分
        ("pic/a.png?v=1", "/dict-res/7/res/pic/a.png?v=1"),
        ("pic/a.png#frag", "/dict-res/7/res/pic/a.png#frag"),
        ("sound://a/x.mp3?d=1#t", "/dict-res/7/res/a/x.mp3?d=1#t"),
        # 属性名两侧的空格、单引号、文件名里的 = 都要能处理
        ("pic/a=b.png", "/dict-res/7/res/pic/a=b.png"),
    ],
)
def test_rewrite_resource_refs_rewrites_internal_resources(raw: str, expected: str) -> None:
    result = rewrite_resource_refs(f'<img src="{raw}">', dictionary_id=7)
    assert result == f'<img src="{expected}">'


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # file:///… 是 MDict 里「词典资源根目录」的写法，斜杠数量与正反斜杠都有实例
        ("file:///down/7/x.gif", "/dict-res/7/res/down/7/x.gif"),
        ("file://media/a.jpg", "/dict-res/7/res/media/a.jpg"),
        ("file:/img/40.jpg", "/dict-res/7/res/img/40.jpg"),
        ("FILE:///Down/X.GIF", "/dict-res/7/res/Down/X.GIF"),
        ("file:\\\\down\\\\7\\\\x.gif", "/dict-res/7/res/down/7/x.gif"),
        # 指到词典外部的写法也改写成资源 URL：它是个 404，而原来的 file:// 在浏览器里
        # 同样打不开，不存在「改坏了」
        ("file:///etc/passwd", "/dict-res/7/res/etc/passwd"),
    ],
)
def test_rewrite_resource_refs_rewrites_file_scheme_to_resource(
    raw: str, expected: str
) -> None:
    result = rewrite_resource_refs(f'<img src="{raw}">', dictionary_id=7)
    assert result == f'<img src="{expected}">'


@pytest.mark.parametrize(
    "raw",
    [
        # 词条内跳转：必须原样保留，由前端点击时拦截并发起新查询
        "entry://apple",
        "entry://#section",
        "entry://a b c",
        # 外部资源
        "https://example.com/a.png",
        "http://example.com/x",
        "//cdn.example.com/x.js",
        "www.example.com/x",
        "mailto:a@b.com",
        "ftp://example.com/x",
        "blob:https://example.com/uuid",
        "tel:+123456",
        # 页内锚点与内联数据
        "#section",
        "data:image/png;base64,AAA",
        # 危险协议：原样保留（前端会拦截点击），绝不改写成看似可执行的样子
        "javascript:alert(1)",
        # 未知协议保守不动
        "ws://example.com/socket",
        # 无扩展名的裸相对路径：MDX 里这种基本是词条链接，补成 /dict-res/ 只会 404
        "apple",
        "some/word",
        "回目录",
    ],
)
def test_rewrite_resource_refs_leaves_non_resource_refs_untouched(raw: str) -> None:
    html = f'<a href="{raw}">x</a>'
    assert rewrite_resource_refs(html, dictionary_id=7) == html


def test_rewrite_resource_refs_leaves_traversal_attempt_unrewritten() -> None:
    html = '<img src="../../etc/passwd">'
    result = rewrite_resource_refs(html, dictionary_id=1)
    # 无法规范化的路径原样保留，不会被拼成看似合法的 /dict-res/ 链接
    assert "/dict-res/" not in result


def test_rewrite_resource_refs_handles_single_quotes_and_spacing() -> None:
    html = "<img src = 'pic/apple.png'>"
    result = rewrite_resource_refs(html, dictionary_id=3)
    assert "/dict-res/3/res/pic/apple.png" in result


def test_rewrite_resource_refs_handles_mixed_document() -> None:
    """一条真实形态的释义：词条链接、图片、外链、发音混在一起。"""
    html = (
        "<style>p{margin:0}</style>"
        '<a href="entry://苹果">苹果</a>'
        '<img src="pic/apple.png">'
        '<a href="sound://audio/guo.spx">🔊</a>'
        '<a href="https://example.com">站外</a>'
    )
    result = rewrite_resource_refs(html, dictionary_id=12)
    assert 'href="entry://苹果"' in result
    assert 'href="/dict-res/12/res/sound:/' not in result
    assert 'src="/dict-res/12/res/pic/apple.png"' in result
    assert 'href="/dict-res/12/res/audio/guo.spx"' in result
    assert 'href="https://example.com"' in result
    assert "<style>p{margin:0}</style>" in result
