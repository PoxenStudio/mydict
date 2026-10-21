import pytest

from app.core.urls import safe_http_url
from app.schemas.vocab import VocabCreateRequest, VocabItemOut


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/a",
        "https://example.com:8443/x?q=1#f",
        "http://localhost:5173/",
        "http://[::1]:8000/x",
        "https://例子.测试/路径",
        "https://example.com./x",
        "HTTPS://Example.COM/A",
        "https://user:pw@example.com/x",
        "https://example.com/%E4%B8%AD",
        "  https://ok.example/x  ",
    ],
)
def test_allows_normal_http_urls(value: str) -> None:
    result = safe_http_url(value)
    assert result is not None
    # 前导/尾随空白会被裁掉，其余原样返回
    assert result == value.strip()


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "javascript:alert(1)",
        "JaVaScRiPt:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
        "mailto:a@b.com",
        "//evil.example/x",
        r"\/evil.example",
        r"http:/\evil.example",
        r"https://\javascript:alert(1)",
        "http:///evil.com",
        "http://",
        "http://user@",
        "https://example.com/\r\nX-Injected: 1",
        "https://example.com/a\tb",
        "https://example.com/a\x00b",
        "https://example.com/a\x7fb",
    ],
)
def test_rejects_dangerous_or_malformed(value: str | None) -> None:
    assert safe_http_url(value) is None


def test_create_request_drops_bad_url_but_keeps_item() -> None:
    """坏链接只丢弃 URL，不影响这条收藏本身。"""
    body = VocabCreateRequest(word="bank", context_sentence="a bank", context_url="javascript:alert(1)")
    assert body.context_url is None
    assert body.word == "bank"

    body = VocabCreateRequest(word="bank", context_url="https://example.com/x")
    assert body.context_url == "https://example.com/x"


def test_output_sanitizes_historical_rows() -> None:
    """库里可能留着修复前的脏值，出库时同样要洗掉。"""
    item = VocabItemOut(
        id=1,
        word="bank",
        phonetic=None,
        definition=None,
        note=None,
        dictionary_id=None,
        created_at="2026-10-20T00:00:00",
        context_url="javascript:alert(1)",
    )
    assert item.context_url is None
