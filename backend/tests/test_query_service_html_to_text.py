from app.services.query_service import html_to_plain_text


def test_html_to_plain_text_strips_tags_and_link() -> None:
    html = (
        '<link rel="stylesheet" type="text/css" href="/dict-res/7/res/x.css" />'
        "<p><strong>豫章</strong></p>"
        "<p>①春秋楚地。</p>"
        "<p>②江西省的别称。</p>\r\n"
    )
    text = html_to_plain_text(html)
    assert "<" not in text
    assert text == "豫章\n①春秋楚地。\n②江西省的别称。"


def test_html_to_plain_text_unescapes_entities() -> None:
    assert html_to_plain_text("<p>a &amp; b &lt;c&gt;</p>") == "a & b <c>"


def test_html_to_plain_text_passthrough_for_plain_text() -> None:
    assert html_to_plain_text("hello\nworld") == "hello\nworld"
