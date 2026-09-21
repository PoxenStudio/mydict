from pathlib import Path

import pytest

from app.services.resource_service import (
    normalize_resource_path,
    rewrite_resource_refs,
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
        "file:///etc/passwd",
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
