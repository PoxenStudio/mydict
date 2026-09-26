"""在线词典查询端点的用例。出站抓取打桩，只验证聚合/鉴权/链接生成。"""

import httpx
from httpx import AsyncClient

from app.services import online_dict_service
from app.services.settings_service import set_setting


async def test_online_lookup_aggregates_sections_and_links(
    client: AsyncClient, admin_headers: dict[str, str], db_session, monkeypatch
) -> None:
    set_setting(db_session, "open_access", "true")
    word = f"在线词{online_dict_service.__name__}{id(monkeypatch)}"

    def fake_wikipedia(w, lang):
        return {"id": "wikipedia", "name": "Wikipedia", "title": w,
                "subtitle": "desc", "text": "摘要", "url": "https://zh.wikipedia.org/wiki/x"}

    def fake_wiktionary(w, lang):
        return {"id": "wiktionary", "name": "Wiktionary", "title": None, "subtitle": None,
                "text": None, "url": None,
                "entries": [{"pos": "noun", "language": "Chinese",
                             "senses": [{"text": "释义", "examples": ["例句"]}]}]}

    def fake_baike(w):
        return None  # 单个源失败不影响其它源

    monkeypatch.setattr(online_dict_service, "_fetch_wikipedia", fake_wikipedia)
    monkeypatch.setattr(online_dict_service, "_fetch_wiktionary", fake_wiktionary)
    monkeypatch.setattr(online_dict_service, "_fetch_baike", fake_baike)

    resp = await client.get("/api/dict/online/lookup", params={"word": word, "lang": "zh"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["word"] == word
    assert [s["id"] for s in data["sections"]] == ["wikipedia", "wiktionary"]
    names = {link["name"] for link in data["links"]}
    assert names == {"Google", "Urban Dictionary", "Merriam-Webster", "Goodreads"}
    # 外部链接带上了查询词
    google = next(link for link in data["links"] if link["name"] == "Google")
    assert "google.com/search" in google["url"]


async def test_online_lookup_all_sources_fail_still_returns_links(
    client: AsyncClient, admin_headers: dict[str, str], db_session, monkeypatch
) -> None:
    set_setting(db_session, "open_access", "true")
    word = f"全失败{online_dict_service.__name__}{id(client)}"

    def fail(*args, **kwargs):
        return None

    monkeypatch.setattr(online_dict_service, "_fetch_wikipedia", fail)
    monkeypatch.setattr(online_dict_service, "_fetch_wiktionary", fail)
    monkeypatch.setattr(online_dict_service, "_fetch_baike", fail)

    resp = await client.get("/api/dict/online/lookup", params={"word": word})
    assert resp.status_code == 200
    data = resp.json()
    assert data["sections"] == []
    assert len(data["links"]) == 4


async def test_online_lookup_filters_disabled_sources(
    client: AsyncClient, admin_headers: dict[str, str], db_session, monkeypatch
) -> None:
    """管理后台的源开关：设置里只留 wikipedia + google，其它 section/外链都不出现。"""
    set_setting(db_session, "open_access", "true")
    set_setting(db_session, "online_dict_sources", "wikipedia,google,不合法id")
    word = f"开关词{online_dict_service.__name__}{id(monkeypatch)}"

    def fake_wikipedia(w, lang):
        return {"id": "wikipedia", "name": "Wikipedia", "title": w,
                "subtitle": "", "text": "摘要", "url": None}

    def fail(*args, **kwargs):
        raise AssertionError("被禁用的源不应该被调用")

    monkeypatch.setattr(online_dict_service, "_fetch_wikipedia", fake_wikipedia)
    monkeypatch.setattr(online_dict_service, "_fetch_wiktionary", fail)
    monkeypatch.setattr(online_dict_service, "_fetch_baike", fail)

    resp = await client.get("/api/dict/online/lookup", params={"word": word, "lang": "zh"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert [s["id"] for s in data["sections"]] == ["wikipedia"]
    assert [link["id"] for link in data["links"]] == ["google"]


async def test_online_lookup_requires_open_access_or_login(
    client: AsyncClient, db_session
) -> None:
    set_setting(db_session, "open_access", "false")
    resp = await client.get("/api/dict/online/lookup", params={"word": "x"})
    assert resp.status_code == 401
