"""iframe 引导脚本里纯函数的用例（用 node 执行，缺 node 时跳过）。

引导脚本依赖 DOM，没法整段跑；这里只把它里面的纯函数抠出来单独验证。被验证的是词条链接
协议的关键分支——Weblio 系词典把 `entry://` 的目标写成百分号编码，不解码就会「点了链接
跳转过去但没有任何内容」，所以这几个断言值得钉住。
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

BOOTSTRAP = Path(__file__).resolve().parents[1] / "app" / "services" / "iframe_bootstrap.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="需要 node 才能执行引导脚本里的纯函数"
)


def _function_source(name: str) -> str:
    """取 `  function name(...) { ... }` 整段（脚本里函数体统一 2 空格缩进的收尾花括号）。"""
    source = BOOTSTRAP.read_text(encoding="utf-8")
    match = re.search(rf"\n  function {name}\(.*?\n  \}}", source, re.S)
    assert match, f"引导脚本里找不到函数 {name}"
    return match.group(0)


def _call_decoder(values: list[str]) -> list[str]:
    script = (
        _function_source("decodeEntryWord")
        + "\nconst input = JSON.parse(process.argv[1]);"
        + "\nconsole.log(JSON.stringify(input.map(decodeEntryWord)));"
    )
    result = subprocess.run(
        ["node", "-e", script, json.dumps(values)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_decode_entry_word_handles_percent_encoded_targets() -> None:
    """Weblio 類語/対義語这类词典：目标词是百分号编码的，必须解码后再交给父页查询。"""
    encoded = [
        "%E9%95%B7%E6%89%80",  # 長所
        "%E5%84%AA%E3%82%8C%E3%81%9F%E7%82%B9",  # 優れた点
        "%E5%8F%96%E3%82%8A%E5%BE%97",  # 取り得
    ]
    assert _call_decoder(encoded) == ["長所", "優れた点", "取り得"]


def test_decode_entry_word_keeps_plain_and_broken_targets() -> None:
    """未编码的词原样通过；含裸百分号或残缺编码的词解不开，宁可原样也不抛错。"""
    assert _call_decoder(["長所", "apple", "50%25", "100%", "%E9"]) == [
        "長所",
        "apple",
        "50%",
        "100%",
        "%E9",
    ]


def test_handle_link_decodes_both_entry_forms() -> None:
    """两条入口都要走解码：标准 entry:// 与历史遗留的 /dict-res/N/res/entry:/x。"""
    source = BOOTSTRAP.read_text(encoding="utf-8")
    assert "decodeEntryWord(base.slice(8))" in source
    assert "decodeEntryWord(rest)" in source


def test_report_has_timer_fallback_for_swallowed_raf() -> None:
    """高度上报不能只靠 requestAnimationFrame。

    `report()` 里 `pending` 是「一次只排一帧」的锁：先置 true，等 rAF 回调 `flush()` 收尾。
    实测桌面端（Tauri + WebKitGTK）的沙箱 srcdoc 子页里 rAF 不执行——首帧丢了以后 pending
    永远为 true，后续所有 report() 都在第一行 return，`mydict:height` 一条都发不出去，父页
    只能停在默认高度把词条裁掉（表现为「词条高度超低、看不到内容」）。所以必须同时挂定时器。
    """
    body = _function_source("report")
    assert "requestAnimationFrame" in body
    assert "setTimeout" in body and "if (pending) flush()" in body
