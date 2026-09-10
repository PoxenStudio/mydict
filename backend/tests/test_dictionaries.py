import csv
import io
import struct

from httpx import AsyncClient

from app.core.config import get_settings
from app.services.settings_service import set_setting


def _ecdict_csv_bytes() -> bytes:
    fieldnames = [
        "word",
        "phonetic",
        "definition",
        "translation",
        "pos",
        "collins",
        "oxford",
        "tag",
        "bnc",
        "frq",
        "exchange",
        "detail",
        "audio",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerow(
        {
            "word": "apple",
            "phonetic": "æpl",
            "definition": "n. a fruit",
            "translation": "苹果",
            "pos": "n",
            "collins": "3",
            "oxford": "1",
            "tag": "",
            "bnc": "",
            "frq": "",
            "exchange": "",
            "detail": "",
            "audio": "",
        }
    )
    writer.writerow({k: "" for k in fieldnames} | {"word": "apricot", "translation": "杏"})
    return buf.getvalue().encode("utf-8")


def _build_stardict_bytes() -> dict[str, bytes]:
    entries = [("hello", "int. 你好"), ("world", "n. 世界")]
    dict_bytes = b""
    idx_bytes = b""
    for word, definition in entries:
        content = definition.encode("utf-8")
        idx_bytes += word.encode("utf-8") + b"\x00"
        idx_bytes += struct.pack(">I", len(dict_bytes))
        idx_bytes += struct.pack(">I", len(content))
        dict_bytes += content
    ifo = (
        "StarDict's dict ifo file\n"
        "version=2.4.2\n"
        "bookname=Greeting\n"
        f"wordcount={len(entries)}\n"
        f"idxfilesize={len(idx_bytes)}\n"
        "sametypesequence=m\n"
    ).encode("utf-8")
    return {"greeting.ifo": ifo, "greeting.idx": idx_bytes, "greeting.dict": dict_bytes}


async def test_upload_ecdict_and_manage_lifecycle(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    import os

    csv_bytes = _ecdict_csv_bytes()
    resp = await client.post(
        "/api/admin/dictionaries",
        headers=admin_headers,
        data={"name": "Mini ECDICT", "format": "ecdict", "lang_from": "en", "lang_to": "zh"},
        files={"files": ("ecdict.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    dictionary = resp.json()
    assert dictionary["word_count"] == 2
    assert dictionary["status"] == "disabled"
    assert dictionary["import_method"] == "upload"
    dict_id = dictionary["id"]

    settings = get_settings()
    source_dir = os.path.join(settings.dictionary_storage_path, str(dict_id), "source")
    assert os.path.exists(source_dir)  # 浏览器上传的文件应归档到 source/

    # 未启用时也允许后台预览测试查询
    resp = await client.get(
        f"/api/admin/dictionaries/{dict_id}/test-query",
        params={"word": "ap"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    words = {e["word"] for e in resp.json()}
    assert words == {"apple", "apricot"}

    resp = await client.put(f"/api/admin/dictionaries/{dict_id}/enable", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "enabled"

    # 导入是同步跑完才返回的，响应回来时任务登记表应该已经清空
    resp = await client.get("/api/admin/tasks/running", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == []

    resp = await client.put(f"/api/admin/dictionaries/{dict_id}/disable", headers=admin_headers)
    assert resp.json()["status"] == "disabled"

    resp = await client.delete(f"/api/admin/dictionaries/{dict_id}", headers=admin_headers)
    assert resp.status_code == 200

    resp = await client.get(
        f"/api/admin/dictionaries/{dict_id}/test-query",
        params={"word": "app"},
        headers=admin_headers,
    )
    assert resp.status_code == 404

    # upload 方式的 source/ 是本应用管理的暂存归档，删除词典应一并清理
    assert not os.path.exists(source_dir)

    # dict_entries 应通过外键 ON DELETE CASCADE 一并删除，不是只删了 dictionaries 那一行
    from app.models.dictionary import DictEntry

    db_session.expire_all()
    assert db_session.query(DictEntry).filter(DictEntry.dictionary_id == dict_id).count() == 0


async def test_update_dictionary_name_and_lang(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    set_setting(db_session, "open_access", "true")
    resp = await client.post(
        "/api/admin/dictionaries",
        headers=admin_headers,
        data={"name": "Mini ECDICT", "format": "ecdict", "lang_from": "en", "lang_to": "zh"},
        files={"files": ("ecdict.csv", _ecdict_csv_bytes(), "text/csv")},
    )
    dict_id = resp.json()["id"]
    await client.put(f"/api/admin/dictionaries/{dict_id}/enable", headers=admin_headers)

    # 改名+改语言方向后查询结果里的词典名要立刻是新的，不能因为查询结果有 5 分钟 TTL 缓存而看到旧名字
    # （lang_from 保持 en 不变，避免连带影响 "apple" 的自动语言路由，改 lang_to 已足够验证字段生效）
    await client.get("/api/dict/search", params={"word": "apple"})
    resp = await client.put(
        f"/api/admin/dictionaries/{dict_id}",
        headers=admin_headers,
        json={"name": "改名后的词典", "lang_from": "en", "lang_to": "zh-Hans"},
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["name"] == "改名后的词典"
    assert updated["lang_from"] == "en"
    assert updated["lang_to"] == "zh-Hans"
    assert updated["format"] == "ecdict"  # format 不允许改

    resp = await client.get("/api/dict/search", params={"word": "apple"})
    assert resp.json()["results"][0]["dictionary_name"] == "改名后的词典"

    resp = await client.put(
        "/api/admin/dictionaries/999999",
        headers=admin_headers,
        json={"name": "x", "lang_from": "en", "lang_to": "zh"},
    )
    assert resp.status_code == 404

    resp = await client.put(
        f"/api/admin/dictionaries/{dict_id}",
        headers=admin_headers,
        json={"name": "", "lang_from": "en", "lang_to": "zh"},
    )
    assert resp.status_code == 422


async def test_running_tasks_requires_admin(client: AsyncClient) -> None:
    resp = await client.get("/api/admin/tasks/running")
    assert resp.status_code == 401


async def test_import_from_dicts_dir_leaves_source_files_in_place(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    settings = get_settings()
    inbox = settings.dicts_inbox_path
    import os

    os.makedirs(inbox, exist_ok=True)
    for name, content in _build_stardict_bytes().items():
        with open(os.path.join(inbox, name), "wb") as f:
            f.write(content)

    resp = await client.get("/api/admin/dictionaries/dicts-dir-files", headers=admin_headers)
    assert resp.status_code == 200
    names = {f["name"] for f in resp.json()["entries"]}
    assert {"greeting.ifo", "greeting.idx", "greeting.dict"} <= names

    resp = await client.post(
        "/api/admin/dictionaries/import-from-dicts-dir",
        headers=admin_headers,
        json={
            "name": "Greeting StarDict",
            "format": "stardict",
            "lang_from": "en",
            "lang_to": "zh",
            "files": ["greeting.ifo", "greeting.idx", "greeting.dict"],
        },
    )
    assert resp.status_code == 200, resp.text
    dictionary = resp.json()
    assert dictionary["word_count"] == 2
    assert dictionary["import_method"] == "dicts_dir"

    # /data/dicts 下的文件是用户自己放进去的，导入不应移动/删除，删不删由用户自己决定
    assert os.path.exists(os.path.join(inbox, "greeting.ifo"))
    source_dir = os.path.join(settings.dictionary_storage_path, str(dictionary["id"]), "source")
    assert not os.path.exists(source_dir)

    # 删除词典同理不应该碰 /data/dicts 下的原始文件
    resp = await client.delete(
        f"/api/admin/dictionaries/{dictionary['id']}", headers=admin_headers
    )
    assert resp.status_code == 200
    assert os.path.exists(os.path.join(inbox, "greeting.ifo"))


async def test_import_from_dicts_dir_rejects_multiple_ecdict_files(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    settings = get_settings()
    inbox = settings.dicts_inbox_path
    import os

    os.makedirs(inbox, exist_ok=True)
    csv_bytes = _ecdict_csv_bytes()
    for name in ("dict_a.csv", "dict_b.csv"):
        with open(os.path.join(inbox, name), "wb") as f:
            f.write(csv_bytes)

    # 选了两个 CSV 一起提交：EcdictParser 只读 file_paths[0]，不拦住会静默只导入第一个，
    # 必须在这里就报错，而不是悄悄丢掉第二个文件。
    resp = await client.post(
        "/api/admin/dictionaries/import-from-dicts-dir",
        headers=admin_headers,
        json={
            "name": "Two CSV",
            "format": "ecdict",
            "lang_from": "en",
            "lang_to": "zh",
            "files": ["dict_a.csv", "dict_b.csv"],
        },
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"

    # 两个都还没导入，dicts-dir-files 里应该都标 imported=false
    resp = await client.get("/api/admin/dictionaries/dicts-dir-files", headers=admin_headers)
    by_name = {f["name"]: f for f in resp.json()["entries"]}
    assert by_name["dict_a.csv"]["imported"] is False
    assert by_name["dict_b.csv"]["imported"] is False

    # 单选一个应该能正常导入，导入后该文件在列表里标为 imported=true，另一个仍是 false
    resp = await client.post(
        "/api/admin/dictionaries/import-from-dicts-dir",
        headers=admin_headers,
        json={
            "name": "Dict A",
            "format": "ecdict",
            "lang_from": "en",
            "lang_to": "zh",
            "files": ["dict_a.csv"],
        },
    )
    assert resp.status_code == 200, resp.text

    resp = await client.get("/api/admin/dictionaries/dicts-dir-files", headers=admin_headers)
    by_name = {f["name"]: f for f in resp.json()["entries"]}
    assert by_name["dict_a.csv"]["imported"] is True
    assert by_name["dict_b.csv"]["imported"] is False


async def test_import_from_dicts_dir_rejects_path_traversal(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.post(
        "/api/admin/dictionaries/import-from-dicts-dir",
        headers=admin_headers,
        json={
            "name": "evil",
            "format": "stardict",
            "lang_from": "en",
            "lang_to": "zh",
            "files": ["../../etc/passwd"],
        },
    )
    assert resp.status_code == 422


async def test_dicts_dir_files_lists_and_imports_from_subdirectory(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    settings = get_settings()
    inbox = settings.dicts_inbox_path
    import os

    sub_dir = os.path.join(inbox, "cn")
    os.makedirs(sub_dir, exist_ok=True)
    with open(os.path.join(sub_dir, "ecdict.csv"), "wb") as f:
        f.write(_ecdict_csv_bytes())
    # 根目录另放一个同名文件，验证按目录区分 imported 状态不会互相误标
    with open(os.path.join(inbox, "ecdict.csv"), "wb") as f:
        f.write(_ecdict_csv_bytes())

    resp = await client.get("/api/admin/dictionaries/dicts-dir-files", headers=admin_headers)
    body = resp.json()
    assert body["path"] == ""
    by_name = {e["name"]: e for e in body["entries"]}
    assert by_name["cn"]["is_dir"] is True
    assert by_name["ecdict.csv"]["is_dir"] is False

    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files",
        params={"path": "cn"},
        headers=admin_headers,
    )
    body = resp.json()
    assert body["path"] == "cn"
    by_name = {e["name"]: e for e in body["entries"]}
    assert by_name["ecdict.csv"]["imported"] is False

    resp = await client.post(
        "/api/admin/dictionaries/import-from-dicts-dir",
        headers=admin_headers,
        json={
            "name": "CN ECDICT",
            "format": "ecdict",
            "lang_from": "zh-Hans",
            "lang_to": "en",
            "files": ["cn/ecdict.csv"],
        },
    )
    assert resp.status_code == 200, resp.text

    # 子目录里的文件标为已导入，根目录下的同名文件不受影响
    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files",
        params={"path": "cn"},
        headers=admin_headers,
    )
    assert {e["name"]: e for e in resp.json()["entries"]}["ecdict.csv"]["imported"] is True
    resp = await client.get("/api/admin/dictionaries/dicts-dir-files", headers=admin_headers)
    assert {e["name"]: e for e in resp.json()["entries"]}["ecdict.csv"]["imported"] is False


async def test_dicts_dir_files_rejects_subdirectory_traversal(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files",
        params={"path": "../etc"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


async def test_delete_dictionary_does_not_block_on_vacuum(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    import time

    resp = await client.post(
        "/api/admin/dictionaries",
        headers=admin_headers,
        data={"name": "Vacuum Timing", "format": "ecdict", "lang_from": "en", "lang_to": "zh"},
        files={"files": ("v.csv", _ecdict_csv_bytes(), "text/csv")},
    )
    dict_id = resp.json()["id"]

    t0 = time.monotonic()
    resp = await client.delete(f"/api/admin/dictionaries/{dict_id}", headers=admin_headers)
    elapsed = time.monotonic() - t0

    assert resp.status_code == 200
    # VACUUM 重写整个数据库文件，库越大越慢（实测 200MB 库要 40+ 秒），必须丢进后台线程，
    # 删除接口本身只做行删除+文件清理就应该返回，不能等 VACUUM 跑完，否则前端 10 秒
    # 超时会显示"删除没反应"，尽管后端其实最终还是删除成功了。
    assert elapsed < 3


async def test_upload_rejects_multiple_ecdict_files(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    csv_bytes = _ecdict_csv_bytes()
    resp = await client.post(
        "/api/admin/dictionaries",
        headers=admin_headers,
        data={"name": "Two CSV Upload", "format": "ecdict", "lang_from": "en", "lang_to": "zh"},
        files=[
            ("files", ("a.csv", csv_bytes, "text/csv")),
            ("files", ("b.csv", csv_bytes, "text/csv")),
        ],
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


async def test_reorder_dictionaries(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    ids = []
    for i in range(3):
        resp = await client.post(
            "/api/admin/dictionaries",
            headers=admin_headers,
            data={"name": f"D{i}", "format": "ecdict", "lang_from": "en", "lang_to": "zh"},
            files={"files": ("d.csv", _ecdict_csv_bytes(), "text/csv")},
        )
        ids.append(resp.json()["id"])

    reversed_ids = list(reversed(ids))
    resp = await client.put(
        "/api/admin/dictionaries/reorder",
        headers=admin_headers,
        json={"ordered_ids": reversed_ids},
    )
    assert resp.status_code == 200
    body = {d["id"]: d["sort_order"] for d in resp.json()}
    for expected_order, dict_id in enumerate(reversed_ids):
        assert body[dict_id] == expected_order


async def test_dictionary_api_requires_admin(client: AsyncClient) -> None:
    resp = await client.get("/api/admin/dictionaries")
    assert resp.status_code == 401


async def test_upload_rejects_mismatched_file_extension(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.post(
        "/api/admin/dictionaries",
        headers=admin_headers,
        data={"name": "bad-ext", "format": "ecdict", "lang_from": "en", "lang_to": "zh"},
        files={"files": ("not-a-dict.exe", b"MZ\x90\x00fake", "application/octet-stream")},
    )
    assert resp.status_code == 422
    assert "not-a-dict.exe" in resp.json()["message"]


async def test_incomplete_stardict_upload_returns_clean_error(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    # 只上传 .ifo，缺少 .idx/.dict：应返回可读的 4xx，而不是未处理异常导致的 500
    resp = await client.post(
        "/api/admin/dictionaries",
        headers=admin_headers,
        data={"name": "incomplete", "format": "stardict", "lang_from": "en", "lang_to": "zh"},
        files={
            "files": (
                "only.ifo",
                b"StarDict's dict ifo file\nversion=2.4.2\nwordcount=0\n",
                "text/plain",
            )
        },
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"
