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


def test_rewrite_resource_refs_rewrites_relative_paths() -> None:
    html = '<img src="pic/apple.png"><a href="snd/apple.mp3">play</a>'
    result = rewrite_resource_refs(html, dictionary_id=7)
    assert 'src="/dict-res/7/res/pic/apple.png"' in result
    assert 'href="/dict-res/7/res/snd/apple.mp3"' in result


def test_rewrite_resource_refs_leaves_external_and_data_urls_untouched() -> None:
    html = (
        '<img src="https://example.com/a.png">'
        '<img src="data:image/png;base64,AAA">'
        '<a href="http://example.com/x">link</a>'
    )
    result = rewrite_resource_refs(html, dictionary_id=1)
    assert result == html


def test_rewrite_resource_refs_leaves_traversal_attempt_unrewritten() -> None:
    html = '<img src="../../etc/passwd">'
    result = rewrite_resource_refs(html, dictionary_id=1)
    # 无法规范化的路径原样保留，不会被拼成看似合法的 /dict-res/ 链接
    assert "/dict-res/" not in result
