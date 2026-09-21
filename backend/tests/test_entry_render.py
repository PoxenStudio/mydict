"""词条 HTML 渲染（iframe 隔离）的用例。

分两部分：
  - `render_entry_document` 的纯函数用例：文档组装、注入位置、必须由我们自己提供的 meta
  - `GET /api/dict/entry/{id}` 的接口用例：鉴权、启用状态、可用词典限制
"""

import csv
import io
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.services.entry_render_service import render_entry_document
from app.services.settings_service import set_setting
from tests.conftest import import_dictionary

# 引导脚本里的独占标识，用来确认它确实被注入了、且插在正确位置
BOOT_MARK = "__mydictBooted"

# 查词菜单样式的特征串。不能用 "mydict-lookup" 当标记——引导脚本的函数体里始终有
# `className = 'mydict-lookup'`，只有样式真被注入才说明这条渲染路径开了菜单。
LOOKUP_STYLE_MARK = ".mydict-lookup{position:fixed"


# --------------------------------------------------------------------- 纯函数


def test_fragment_is_wrapped_in_full_document() -> None:
    html = render_entry_document("<p>苹果，一种水果</p>", dictionary_id=7)
    assert html.startswith("<!DOCTYPE html>")
    assert "<html" in html and "<head>" in html and "<body>" in html
    assert "<p>苹果，一种水果</p>" in html


def test_bootstrap_and_dictionary_id_are_injected() -> None:
    html = render_entry_document("<p>x</p>", dictionary_id=42)
    assert BOOT_MARK in html
    # 占位符必须被替换成真实 id，脚本才能拼出 /dict-res/42/res/ 前缀
    assert "__MYDICT_DICT_ID__" not in html
    assert "var DICT_ID = 42" in html


def test_document_carries_its_own_referrer_and_csp() -> None:
    html = render_entry_document("<p>x</p>", dictionary_id=1)
    assert 'name="referrer" content="no-referrer"' in html
    # CSP 只声明与 sandbox 属性一致的 allow-scripts：不限制子资源加载（否则词典的
    # 图片/CSS/字体会被拦掉），作用是在 sandbox 属性被误删时仍兜住一层
    assert 'http-equiv="Content-Security-Policy" content="sandbox allow-scripts"' in html
    assert 'charset="utf-8"' in html


def test_full_document_is_not_nested() -> None:
    """词条本身是完整文档时不能再套一层 html —— 嵌套会触发怪异模式、也会破坏它的 meta。"""
    definition = "<!DOCTYPE html><html><head><title>t</title></head><body><p>正文</p></body></html>"
    html = render_entry_document(definition, dictionary_id=5)
    assert html.count("<html") == 1
    assert html.count("<!DOCTYPE html>") == 1
    assert "<p>正文</p>" in html


def test_bootstrap_precedes_dictionary_own_script() -> None:
    """引导脚本必须先于词典自带脚本执行，否则它一抛错就装不上高度上报与链接拦截。"""
    definition = "<html><head><script>var fromDictionary=1</script></head><body>x</body></html>"
    html = render_entry_document(definition, dictionary_id=3)
    assert html.index(BOOT_MARK) < html.index("fromDictionary")


def test_full_document_without_head_injects_after_html() -> None:
    definition = "<html><body><p>y</p></body></html>"
    html = render_entry_document(definition, dictionary_id=9)
    assert html.index(BOOT_MARK) < html.index("<body>")
    assert html.count("<html") == 1


def test_full_document_without_html_or_head_prepends() -> None:
    definition = "<!doctype html><p>裸内容</p>"
    html = render_entry_document(definition, dictionary_id=2)
    assert html.index(BOOT_MARK) < html.index("<p>裸内容</p>")


def test_definition_html_is_passed_through_untouched() -> None:
    """不做净化：词典的 style/class/表格必须原样保留，否则排版全废。"""
    definition = '<style>p{margin:0}</style><table class="t"><tr><td>甲</td></tr></table>'
    html = render_entry_document(definition, dictionary_id=1)
    assert definition in html


def test_script_in_definition_is_preserved_for_the_iframe() -> None:
    """词典自带的脚本要保留（在 iframe 里跑），隔离由 sandbox 负责而不是靠删标签。"""
    definition = '<script>document.title="x"</script><p>z</p>'
    html = render_entry_document(definition, dictionary_id=1)
    assert '<script>document.title="x"</script>' in html


def test_dark_theme_style_is_injected() -> None:
    """词典原文常把颜色写死（白底黑字），暗色下要靠这段样式翻掉。"""
    html = render_entry_document("<p>x</p>", dictionary_id=1)
    assert "html[data-mydict-theme='dark']" in html
    assert "color-scheme:dark" in html


def test_theme_style_avoids_wildcard_override() -> None:
    """只能翻「明确写着黑/白」的呈现。

    用通配选择器覆盖会连词典自带的红字、彩色表格一起抹平，那就不是「暗色适配」而是
    「把排版改掉」了。
    """
    from app.services.entry_render_service import _THEME_STYLE

    assert "[color='#000' i]" in _THEME_STYLE
    assert "[style*='background:#fff' i]" in _THEME_STYLE
    # 去掉空格后仍不应出现通配选择器
    assert "*{" not in _THEME_STYLE.replace(" ", "")


def test_theme_style_has_no_document_tags() -> None:
    """样式文本里不能出现 <html / <body / <!DOCTYPE。

    这几段会被插进词典自己的 <head>，一旦带上这些字面量，就会破坏
    「文档不重复嵌套」「引导脚本早于 body」这两类结构断言。
    """
    from app.services.entry_render_service import _THEME_STYLE

    lowered = _THEME_STYLE.lower()
    for tag in ("<html", "<body", "<!doctype"):
        assert tag not in lowered


def test_theme_style_precedes_bootstrap() -> None:
    """样式排在引导脚本之前：它不依赖脚本，早一步应用就少一帧白闪。"""
    html = render_entry_document("<p>x</p>", dictionary_id=1)
    assert html.index("data-mydict-theme") < html.index(BOOT_MARK)


def test_theme_is_written_into_the_document_when_given() -> None:
    """带上 theme 就把明暗直接写进文档，iframe 首屏才不会先白一下再变色。"""
    dark = render_entry_document("<p>x</p>", dictionary_id=1, theme="dark")
    assert "setAttribute('data-mydict-theme','dark')" in dark

    light = render_entry_document("<p>x</p>", dictionary_id=1, theme="light")
    assert "setAttribute('data-mydict-theme','light')" in light

    # 不传主题时不写初值，交给子页按系统偏好兜底（兼容不带该参数的调用方）
    unset = render_entry_document("<p>x</p>", dictionary_id=1)
    assert "data-mydict-theme','dark'" not in unset
    assert "data-mydict-theme','light'" not in unset


def test_bootstrap_accepts_theme_command() -> None:
    """父页运行中切换主题时通过 mydict:cmd 下发，引导脚本必须认这条指令。"""
    html = render_entry_document("<p>x</p>", dictionary_id=1)
    assert "data.cmd === 'theme'" in html


def test_bootstrap_boosts_dark_text_in_dark_theme() -> None:
    """词典写死的深色（深蓝最常见）在暗色下必须自动提亮，否则根本看不清。

    写死的颜色值枚举不完，所以走的是运行时读计算颜色再按同色相提亮，而不是 CSS 选择器。
    """
    html = render_entry_document("<p>x</p>", dictionary_id=1)
    assert "boostDarkText" in html
    assert "hsl(from rgb(" in html


# ------------------------------------------------------------- 选中文字查词


def test_lookup_menu_is_opt_in() -> None:
    """选中查词的菜单只在明确要求时注入。

    它需要有查词框接得住（点【查词】最后是发 mydict:entry 给父页去查），生词本与管理端
    预览没有这个东西，所以那两处连菜单都不该出现。
    """
    with_lookup = render_entry_document("<p>x</p>", dictionary_id=1, allow_lookup=True)
    without = render_entry_document("<p>x</p>", dictionary_id=1)

    assert LOOKUP_STYLE_MARK in with_lookup
    assert LOOKUP_STYLE_MARK not in without
    assert "var ALLOW_LOOKUP = true" in with_lookup
    assert "var ALLOW_LOOKUP = false" in without
    # 开关占位符必须被替换掉，否则内联脚本直接是语法错误
    assert "__MYDICT_LOOKUP__" not in with_lookup
    assert "__MYDICT_LOOKUP__" not in without


def test_lookup_style_has_no_document_tags() -> None:
    """菜单样式同样不能带文档级标签——它会被插进词典自己的 <head>。"""
    from app.services.entry_render_service import _LOOKUP_STYLE

    lowered = _LOOKUP_STYLE.lower()
    for tag in ("<html", "<body", "<!doctype"):
        assert tag not in lowered


def test_inline_sources_never_close_the_script_tag() -> None:
    """引导脚本与注入的样式都是内联的，正文里出现 </script 会把文档截断。

    后果是整个词条页白屏 + 高度上报失效。这条守卫防的是以后往里面写注释时手滑。
    """
    from app.services.entry_render_service import (
        _LOOKUP_STYLE,
        _THEME_STYLE,
        _bootstrap_source,
    )

    for chunk in (_bootstrap_source(), _THEME_STYLE, _LOOKUP_STYLE):
        assert "</script" not in chunk.lower()


def test_bootstrap_installs_lookup_menu() -> None:
    html = render_entry_document("<p>x</p>", dictionary_id=1, allow_lookup=True)
    assert "installLookupMenu" in html


# ----------------------------------------------------------------------- 接口


def _ecdict_csv(rows: list[dict[str, str]]) -> bytes:
    fieldnames = ["word", "phonetic", "definition", "translation", "exchange"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue().encode("utf-8")


async def _make_dictionary(
    client: AsyncClient, admin_headers: dict[str, str], name: str, *, enable: bool = True
) -> int:
    dictionary = await import_dictionary(
        client,
        admin_headers,
        data={"name": name, "format": "ecdict", "lang_from": "en", "lang_to": "zh-Hans"},
        files={
            "files": (
                f"{name}.csv",
                _ecdict_csv([{"word": "entryword", "translation": "释义"}]),
                "text/csv",
            )
        },
    )
    if enable:
        resp = await client.put(
            f"/api/admin/dictionaries/{dictionary['id']}/enable", headers=admin_headers
        )
        assert resp.status_code == 200
    return dictionary["id"]


async def _user_headers(client: AsyncClient, name: str) -> dict[str, str]:
    await client.post("/api/auth/register", json={"username": name, "password": "entrypass123"})
    resp = await client.post("/api/auth/login", json={"username": name, "password": "entrypass123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_entry_requires_login_or_open_access(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    dict_id = await _make_dictionary(client, admin_headers, "词条鉴权")
    # 显式关掉「开放使用」：库是整轮测试共用的，别的用例可能已经把它打开过
    set_setting(db_session, "open_access", "false")
    resp = await client.get(f"/api/dict/entry/{dict_id}", params={"word": "entryword"})
    assert resp.status_code == 401


async def test_entry_returns_isolated_html_document(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    dict_id = await _make_dictionary(client, admin_headers, "词条渲染")
    set_setting(db_session, "open_access", "true")

    resp = await client.get(f"/api/dict/entry/{dict_id}", params={"word": "entryword"})
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert BOOT_MARK in body
    assert f"var DICT_ID = {dict_id}" in body
    assert "释义" in body
    # 引导脚本里对词条内跳转与音频的兼容逻辑必须在同一份文档里
    assert "mydict:entry" in body and "mydict:height" in body


@pytest.mark.parametrize("word", ["nosuchword"])
async def test_entry_unknown_word_returns_404(
    client: AsyncClient, admin_headers: dict[str, str], db_session, word: str
) -> None:
    dict_id = await _make_dictionary(client, admin_headers, "词条缺词")
    set_setting(db_session, "open_access", "true")
    resp = await client.get(f"/api/dict/entry/{dict_id}", params={"word": word})
    assert resp.status_code == 404


async def test_entry_unknown_dictionary_returns_404(client: AsyncClient, db_session) -> None:
    set_setting(db_session, "open_access", "true")
    resp = await client.get("/api/dict/entry/999999", params={"word": "entryword"})
    assert resp.status_code == 404


async def test_entry_disabled_dictionary_returns_404(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    dict_id = await _make_dictionary(client, admin_headers, "词条停用", enable=False)
    set_setting(db_session, "open_access", "true")
    resp = await client.get(f"/api/dict/entry/{dict_id}", params={"word": "entryword"})
    assert resp.status_code == 404


async def test_entry_respects_user_allowed_dictionaries(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    allowed = await _make_dictionary(client, admin_headers, "词条允许")
    denied = await _make_dictionary(client, admin_headers, "词条拒绝")
    headers = await _user_headers(client, "entryuser")
    resp = await client.put(
        "/api/auth/allowed-dictionaries", headers=headers, json={"dictionary_ids": [allowed]}
    )
    assert resp.status_code == 200

    ok = await client.get(
        f"/api/dict/entry/{allowed}", params={"word": "entryword"}, headers=headers
    )
    assert ok.status_code == 200

    # 不能靠直接指定 dictionary_id 绕过「可用词典」限制
    blocked = await client.get(
        f"/api/dict/entry/{denied}", params={"word": "entryword"}, headers=headers
    )
    assert blocked.status_code == 404


async def test_admin_entry_works_for_disabled_dictionary(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """管理端「测试查询」的对象常常正是还没启用的词典，不能被启用状态挡住。"""
    dict_id = await _make_dictionary(client, admin_headers, "管理端预览", enable=False)

    resp = await client.get(
        f"/api/admin/dictionaries/{dict_id}/entry",
        params={"word": "entryword"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/html")
    assert BOOT_MARK in resp.text
    assert "释义" in resp.text


async def test_admin_entry_requires_admin(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    dict_id = await _make_dictionary(client, admin_headers, "管理端鉴权")
    resp = await client.get(
        f"/api/admin/dictionaries/{dict_id}/entry", params={"word": "entryword"}
    )
    assert resp.status_code == 401


async def test_admin_entry_unknown_word_returns_404(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    dict_id = await _make_dictionary(client, admin_headers, "管理端缺词")
    resp = await client.get(
        f"/api/admin/dictionaries/{dict_id}/entry",
        params={"word": "nosuchword"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


async def test_dict_res_sets_cors_header(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """不透明源下加载 @font-face / XHR 都算跨域，缺这个头会让词典自带字体静默失效。"""
    dict_id = await _make_dictionary(client, admin_headers, "资源跨域")
    res_dir = Path(get_settings().dictionary_storage_path) / str(dict_id) / "res" / "font"
    res_dir.mkdir(parents=True, exist_ok=True)
    (res_dir / "a.woff").write_bytes(b"fake-font")

    resp = await client.get(f"/dict-res/{dict_id}/res/font/a.woff")
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "*"
    assert "max-age" in resp.headers.get("cache-control", "")


async def test_dict_res_still_rejects_traversal(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    dict_id = await _make_dictionary(client, admin_headers, "资源越权")
    resp = await client.get(f"/dict-res/{dict_id}/res/../../secret")
    assert resp.status_code in (404, 400)


async def test_entry_honours_theme_param(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """前端按当前主题带上 theme，服务端要把明暗写进文档。"""
    dict_id = await _make_dictionary(client, admin_headers, "词条主题")
    set_setting(db_session, "open_access", "true")

    resp = await client.get(
        f"/api/dict/entry/{dict_id}", params={"word": "entryword", "theme": "dark"}
    )
    assert resp.status_code == 200, resp.text
    assert "setAttribute('data-mydict-theme','dark')" in resp.text


async def test_entry_rejects_unknown_theme(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """只认 light/dark，别的值直接 422，不静默当成某个主题。"""
    dict_id = await _make_dictionary(client, admin_headers, "词条主题非法")
    set_setting(db_session, "open_access", "true")

    resp = await client.get(
        f"/api/dict/entry/{dict_id}", params={"word": "entryword", "theme": "neon"}
    )
    assert resp.status_code == 422


async def test_lookup_menu_only_on_public_entry(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """三个渲染入口里只有前台查询页带查词菜单——另两处没有查词框能接住它。"""
    dict_id = await _make_dictionary(client, admin_headers, "查词菜单分流")
    set_setting(db_session, "open_access", "true")

    public = await client.get(f"/api/dict/entry/{dict_id}", params={"word": "entryword"})
    assert public.status_code == 200, public.text
    assert LOOKUP_STYLE_MARK in public.text

    admin = await client.get(
        f"/api/admin/dictionaries/{dict_id}/entry",
        params={"word": "entryword"},
        headers=admin_headers,
    )
    assert admin.status_code == 200, admin.text
    assert LOOKUP_STYLE_MARK not in admin.text
