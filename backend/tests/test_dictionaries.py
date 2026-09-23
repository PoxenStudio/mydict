import csv
import io
import os
import struct
from pathlib import Path

from httpx import AsyncClient

from app.core.config import get_settings
from app.services.settings_service import set_setting
from tests.conftest import import_dictionary, import_from_dicts_dir, wait_for_task


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
    dictionary = await import_dictionary(
        client,
        admin_headers,
        data={"name": "Mini ECDICT", "format": "ecdict", "lang_from": "en", "lang_to": "zh"},
        files={"files": ("ecdict.csv", csv_bytes, "text/csv")},
    )
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

    # import_dictionary 已经等到任务变成 success 才返回，此时任务不再是 running 状态，
    # 不应出现在 running 列表里
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
    dictionary = await import_dictionary(
        client,
        admin_headers,
        data={"name": "Mini ECDICT", "format": "ecdict", "lang_from": "en", "lang_to": "zh"},
        files={"files": ("ecdict.csv", _ecdict_csv_bytes(), "text/csv")},
    )
    dict_id = dictionary["id"]
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

    dictionary = await import_from_dicts_dir(
        client,
        admin_headers,
        json={
            "name": "Greeting StarDict",
            "format": "stardict",
            "lang_from": "en",
            "lang_to": "zh",
            "files": ["greeting.ifo", "greeting.idx", "greeting.dict"],
        },
    )
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
    await import_from_dicts_dir(
        client,
        admin_headers,
        json={
            "name": "Dict A",
            "format": "ecdict",
            "lang_from": "en",
            "lang_to": "zh",
            "files": ["dict_a.csv"],
        },
    )

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

    await import_from_dicts_dir(
        client,
        admin_headers,
        json={
            "name": "CN ECDICT",
            "format": "ecdict",
            "lang_from": "zh-Hans",
            "lang_to": "en",
            "files": ["cn/ecdict.csv"],
        },
    )

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

    dictionary = await import_dictionary(
        client,
        admin_headers,
        data={"name": "Vacuum Timing", "format": "ecdict", "lang_from": "en", "lang_to": "zh"},
        files={"files": ("v.csv", _ecdict_csv_bytes(), "text/csv")},
    )
    dict_id = dictionary["id"]

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
        dictionary = await import_dictionary(
            client,
            admin_headers,
            data={"name": f"D{i}", "format": "ecdict", "lang_from": "en", "lang_to": "zh"},
            files={"files": ("d.csv", _ecdict_csv_bytes(), "text/csv")},
        )
        ids.append(dictionary["id"])

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
    # 只上传 .ifo，缺少 .idx/.dict：文件名后缀本身合法，校验通不过要等解析阶段才发现，
    # 这一步发生在后台任务里，所以请求本身照常拿到 task_id，需要轮询任务状态才能看到
    # 可读的错误信息，而不是未处理异常导致的 500 或是被吞掉。
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
    assert resp.status_code == 200, resp.text
    task = await wait_for_task(client, admin_headers, resp.json()["task_id"])
    assert task["status"] == "error"
    assert task["error"]


# --- 从服务器目录导入：自动归组与语言自动识别 ---
# 目录扫描的用例统一写进各自的 scan-<name> 子目录：整个测试会话共用同一个 /data/dicts，
# 只有各用各的子目录才能对归组结果做精确断言，不受其它用例留下的文件干扰。


def _write_scratch(name: str, files: dict[str, bytes]) -> str:
    """把文件写进 scan-<name> 子目录，返回相对 /data/dicts 的路径。"""
    inbox = get_settings().dicts_inbox_path
    rel = f"scan-{name}"
    for filename, content in files.items():
        target = os.path.join(inbox, rel, filename)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(content)
    return rel


def _groups_of(body: dict) -> dict[str, dict]:
    return {g["key"]: g for g in body["dictionaries"]}


def _ecdict_csv_bytes_many(count: int = 20) -> bytes:
    """足量行数的英汉 ECDICT 样本，用于验证语言方向的自动识别。"""
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
    for i in range(count):
        writer.writerow(
            {k: "" for k in fieldnames}
            | {"word": f"apple{i:03d}", "translation": "苹果，一种落叶乔木的果实"}
        )
    return buf.getvalue().encode("utf-8")


async def test_dicts_dir_scan_groups_stardict_and_uses_bookname(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    rel = _write_scratch("basic", _build_stardict_bytes())

    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files", params={"path": rel}, headers=admin_headers
    )
    assert resp.status_code == 200
    group = _groups_of(resp.json())["stardict:greeting"]

    assert group["format"] == "stardict"
    # 名称优先取 .ifo 的 bookname，省掉手填
    assert group["name"] == "Greeting"
    assert group["importable"] is True
    assert group["reason"] is None
    assert group["imported"] is False
    assert [f["relpath"] for f in group["files"]] == [
        f"{rel}/greeting.dict",
        f"{rel}/greeting.idx",
        f"{rel}/greeting.ifo",
    ]
    assert group["total_size"] == sum(f["size"] for f in group["files"])


async def test_dicts_dir_scan_keeps_same_stem_formats_apart(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """同主干的 .mdx 与 .ifo 是两部不同格式的词典，不能因为主干相同并成一组。"""
    rel = _write_scratch(
        "merge",
        {
            "foo.mdx": b"m" * 10,
            "foo.mdd": b"m" * 10,
            "foo.ifo": b"StarDict's dict ifo file\nbookname=Foo StarDict\n",
            "foo.idx": b"i" * 10,
            "foo.dict": b"d" * 10,
        },
    )

    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files", params={"path": rel}, headers=admin_headers
    )
    groups = _groups_of(resp.json())

    assert set(groups) == {"mdict:foo", "stardict:foo"}
    assert groups["mdict:foo"]["format"] == "mdict"
    assert groups["stardict:foo"]["format"] == "stardict"
    assert groups["stardict:foo"]["name"] == "Foo StarDict"


async def test_dicts_dir_scan_handles_double_suffix_and_case(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """x.idx.gz / x.dict.dz 是双后缀，且文件名大小写不应影响归组。"""
    rel = _write_scratch(
        "suffix",
        {
            "X.IFO": b"StarDict's dict ifo file\nbookname=Upper Case\n",
            "X.IDX.GZ": b"",
            "X.DICT.DZ": b"",
        },
    )

    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files", params={"path": rel}, headers=admin_headers
    )
    groups = _groups_of(resp.json())

    assert list(groups) == ["stardict:x"]
    assert groups["stardict:x"]["importable"] is True
    assert groups["stardict:x"]["name"] == "Upper Case"


async def test_dicts_dir_scan_marks_incomplete_groups_unimportable(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    rel = _write_scratch(
        "incomplete",
        {"solo.mdd": b"m" * 10, "only.ifo": b"StarDict's dict ifo file\nbookname=Only\n"},
    )

    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files", params={"path": rel}, headers=admin_headers
    )
    groups = _groups_of(resp.json())

    # 残缺文件仍然列出来（让人看到），但明确标成不可导入并说明缺什么
    assert groups["mdict:solo"]["importable"] is False
    assert ".mdx" in groups["mdict:solo"]["reason"]
    assert [f["name"] for f in groups["mdict:solo"]["files"]] == ["solo.mdd"]

    assert groups["stardict:only"]["importable"] is False
    assert ".idx" in groups["stardict:only"]["reason"]


async def test_dicts_dir_scan_skips_unrelated_files(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    rel = _write_scratch(
        "skipped",
        {"readme.txt": b"hello", "cover.png": b"\x89PNG", "solo.csv": b"word,translation\n"},
    )

    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files", params={"path": rel}, headers=admin_headers
    )
    body = resp.json()

    # 忽略的文件按相对 /data/dicts 的路径给出，递归扫描时不同目录下的同名文件才区分得开
    assert body["skipped"] == [f"{rel}/cover.png", f"{rel}/readme.txt"]
    assert list(_groups_of(body)) == ["ecdict:solo"]


async def test_dicts_dir_scan_separates_multiple_ecdict_csvs(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """ECDICT 一个 CSV 就是一部完整词典，多个 CSV 必须各自成组而不是被并在一起。"""
    rel = _write_scratch(
        "csvs",
        {"dict_a.csv": b"word,translation\napple,fruit\n", "dict_b.csv": b"word,translation\n"},
    )

    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files", params={"path": rel}, headers=admin_headers
    )
    groups = _groups_of(resp.json())

    assert set(groups) == {"ecdict:dict_a", "ecdict:dict_b"}
    for key, expected in (("ecdict:dict_a", "dict_a"), ("ecdict:dict_b", "dict_b")):
        assert groups[key]["name"] == expected
        assert len(groups[key]["files"]) == 1
        assert groups[key]["importable"] is True


async def test_dicts_dir_scan_marks_imported_after_import(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    rel = _write_scratch("imported", _build_stardict_bytes())
    stardict_files = _build_stardict_bytes()

    await import_from_dicts_dir(
        client,
        admin_headers,
        json={
            "name": "Scan Imported",
            "format": "stardict",
            "lang_from": "en",
            "lang_to": "zh",
            "files": [f"{rel}/{name}" for name in stardict_files],
        },
    )

    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files", params={"path": rel}, headers=admin_headers
    )
    group = _groups_of(resp.json())["stardict:greeting"]

    assert group["imported"] is True
    assert all(f["imported"] is True for f in group["files"])


async def test_dicts_dir_scan_is_non_recursive(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    rel = _write_scratch("nested", {"inner/ecdict.csv": _ecdict_csv_bytes_many(2)})

    # 只扫当前层：看得到 inner 目录，但看不到它里面的 CSV
    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files", params={"path": rel}, headers=admin_headers
    )
    body = resp.json()
    assert body["dictionaries"] == []
    assert {e["name"]: e for e in body["entries"]}["inner"]["is_dir"] is True

    # 进到子目录才归组，且 relpath 带上子目录前缀
    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files",
        params={"path": f"{rel}/inner"},
        headers=admin_headers,
    )
    groups = _groups_of(resp.json())
    assert list(groups) == ["ecdict:ecdict"]
    assert groups["ecdict:ecdict"]["files"][0]["relpath"] == f"{rel}/inner/ecdict.csv"


async def test_dicts_dir_files_requires_admin(client: AsyncClient) -> None:
    resp = await client.get("/api/admin/dictionaries/dicts-dir-files")
    assert resp.status_code == 401


async def test_dicts_dir_scan_merges_multi_volume_mdd(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """MDict 超限时会拆卷成 X.mdd / X.1.mdd / X.2.mdd。

    这些卷必须并进 X.mdx 那一组：否则既会多出一堆「缺少 .mdx」的假分组，导入时也会漏掉
    这些资源（真实词典库里 7 部词典的多卷资源都踩过这个坑）。
    """
    rel = _write_scratch(
        "volume",
        {
            "big.mdx": b"x" * 10,
            "big.mdd": b"r" * 10,
            "big.1.mdd": b"r" * 20,
            "big.2.mdd": b"r" * 30,
        },
    )

    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files", params={"path": rel}, headers=admin_headers
    )
    body = resp.json()
    groups = _groups_of(body)

    assert list(groups) == ["mdict:big"]
    assert groups["mdict:big"]["importable"] is True
    # 名称与主干取 .mdx 的，不能被排序在前面的「big.1」占了
    assert groups["mdict:big"]["name"] == "big"
    assert [f["name"] for f in groups["mdict:big"]["files"]] == [
        "big.1.mdd",
        "big.2.mdd",
        "big.mdd",
        "big.mdx",
    ]
    assert groups["mdict:big"]["total_size"] == 70
    assert body["skipped"] == []


async def test_dicts_dir_scan_keeps_orphan_mdd_separate(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """没有同名 .mdx 的 .1.mdd 不能被当成谁的卷吞掉，仍要单独列出并标缺件。"""
    rel = _write_scratch("orphan", {"lonely.1.mdd": b"r" * 10, "lonely.mdx": b"x" * 10})

    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files", params={"path": rel}, headers=admin_headers
    )
    groups = _groups_of(resp.json())

    # lonely.1.mdd 能对上 lonely.mdx，属于正常并卷
    assert list(groups) == ["mdict:lonely"]
    assert groups["mdict:lonely"]["importable"] is True

    # 换成对不上的主干就该自成一组的缺件项
    rel2 = _write_scratch("orphan2", {"stray.1.mdd": b"r" * 10, "other.mdx": b"x" * 10})
    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files", params={"path": rel2}, headers=admin_headers
    )
    groups2 = _groups_of(resp.json())
    assert set(groups2) == {"mdict:stray.1", "mdict:other"}
    assert groups2["mdict:stray.1"]["importable"] is False
    assert "缺少 .mdx" in groups2["mdict:stray.1"]["reason"]


async def test_dicts_dir_scan_recursive_finds_nested_dictionaries(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """递归扫描要把各子目录里的词典都列出来——用户的词典就是一文件夹一部。"""
    stardict = _build_stardict_bytes()
    rel = _write_scratch(
        "recursive",
        {"alpha/" + name: content for name, content in stardict.items()}
        | {"beta/nested.csv": _ecdict_csv_bytes_many(2)},
    )

    # 不递归时根目录下没有文件，应该是空的
    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files", params={"path": rel}, headers=admin_headers
    )
    assert resp.json()["dictionaries"] == []

    # 递归后两部都出现，并带上各自所在目录
    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files",
        params={"path": rel, "recursive": True},
        headers=admin_headers,
    )
    groups = _groups_of(resp.json())
    assert set(groups) == {"stardict:greeting", "ecdict:nested"}
    assert groups["stardict:greeting"]["dir"] == f"{rel}/alpha"
    assert groups["ecdict:nested"]["dir"] == f"{rel}/beta"
    assert all(g["importable"] for g in groups.values())


async def test_dicts_dir_scan_recursive_uses_directory_name(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """一个文件夹只有一部词典时用目录名当名称：目录名通常比文件名主干可读得多。"""
    rel = _write_scratch(
        "dirname",
        {"[英] 韦氏大学词典/[英-英]语音版图文版UglyFileName.mdx": b"x" * 10},
    )

    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files",
        params={"path": rel, "recursive": True},
        headers=admin_headers,
    )
    groups = _groups_of(resp.json())

    assert list(groups) == ["mdict:[英-英]语音版图文版uglyfilename"]
    assert groups[list(groups)[0]]["name"] == "[英] 韦氏大学词典"


async def test_dicts_dir_scan_recursive_falls_back_when_dir_has_multiple(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """同一目录里放了两部词典时目录名无法区分它们，退回用文件名主干。"""
    rel = _write_scratch(
        "multi",
        {"two/first.mdx": b"x" * 10, "two/second.mdx": b"x" * 10},
    )

    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files",
        params={"path": rel, "recursive": True},
        headers=admin_headers,
    )
    names = sorted(g["name"] for g in resp.json()["dictionaries"])

    assert names == ["first", "second"]


async def test_dicts_dir_scan_recursive_skips_hidden_dirs(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    rel = _write_scratch("hidden", {".git/objects.mdx": b"x" * 10, "ok.mdx": b"x" * 10})

    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files",
        params={"path": rel, "recursive": True},
        headers=admin_headers,
    )
    groups = _groups_of(resp.json())

    assert list(groups) == ["mdict:ok"]


async def test_dicts_dir_scan_recursive_skips_symlinked_dirs(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    rel = _write_scratch("symlink", {"real/ok.mdx": b"x" * 10})
    base = Path(get_settings().dicts_inbox_path) / rel
    os.symlink(base, base / "real" / "loop", target_is_directory=True)

    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files",
        params={"path": rel, "recursive": True},
        headers=admin_headers,
    )

    assert resp.status_code == 200
    assert [g["relpath"] for d in resp.json()["dictionaries"] for g in d["files"]] == [
        f"{rel}/real/ok.mdx"
    ]


async def test_dicts_dir_scan_skips_unreadable_dir(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    rel = _write_scratch("unreadable", {"ok.mdx": b"x" * 10, "locked/hidden.mdx": b"x" * 10})
    locked = Path(get_settings().dicts_inbox_path) / rel / "locked"
    locked.chmod(0)
    try:
        resp = await client.get(
            "/api/admin/dictionaries/dicts-dir-files",
            params={"path": rel, "recursive": True},
            headers=admin_headers,
        )
    finally:
        locked.chmod(0o755)

    assert resp.status_code == 200
    assert list(_groups_of(resp.json())) == ["mdict:ok"]


async def test_dicts_dir_scan_recursive_respects_depth_limit(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """深度有上限，避免误选到一棵巨大的目录树时把整棵树都走一遍。"""
    rel = _write_scratch(
        "depth",
        {
            "d1/d2/d3/d4/shallow.mdx": b"x" * 10,
            "d1/d2/d3/d4/d5/too-deep.mdx": b"x" * 10,
        },
    )

    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files",
        params={"path": rel, "recursive": True},
        headers=admin_headers,
    )
    groups = _groups_of(resp.json())

    assert list(groups) == ["mdict:shallow"]


async def test_dicts_dir_scan_recursive_marks_imported(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """递归扫描里已导入的组同样要标出来，重复跑批量时才会默认跳过。"""
    stardict_files = _build_stardict_bytes()
    rel = _write_scratch(
        "rec-imported", {"sub/" + name: content for name, content in stardict_files.items()}
    )

    await import_from_dicts_dir(
        client,
        admin_headers,
        json={
            "name": "Recursive Imported",
            "format": "stardict",
            "lang_from": "en",
            "lang_to": "zh",
            "files": [f"{rel}/sub/{name}" for name in _build_stardict_bytes()],
        },
    )

    resp = await client.get(
        "/api/admin/dictionaries/dicts-dir-files",
        params={"path": rel, "recursive": True},
        headers=admin_headers,
    )
    group = _groups_of(resp.json())["stardict:greeting"]

    assert group["imported"] is True
    assert all(f["imported"] is True for f in group["files"])


async def test_import_from_dicts_dir_detects_language_when_omitted(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """不带 lang_from/lang_to 时由服务端自动识别，并把结果透出到任务结果里。"""
    rel = _write_scratch("lang", {"auto.csv": _ecdict_csv_bytes_many()})

    resp = await client.post(
        "/api/admin/dictionaries/import-from-dicts-dir",
        headers=admin_headers,
        json={"name": "Auto Lang", "format": "ecdict", "files": [f"{rel}/auto.csv"]},
    )
    assert resp.status_code == 200, resp.text
    task = await wait_for_task(client, admin_headers, resp.json()["task_id"])
    assert task["status"] == "success", task

    # 词头是英文、释义是中文 → en → zh-Hans
    assert task["result"]["lang_from"] == "en"
    assert task["result"]["lang_to"] == "zh-Hans"

    listing = await client.get("/api/admin/dictionaries", headers=admin_headers)
    dictionary = next(d for d in listing.json() if d["id"] == task["result"]["dictionary_id"])
    assert dictionary["lang_from"] == "en"
    assert dictionary["lang_to"] == "zh-Hans"


async def test_import_from_dicts_dir_keeps_explicit_language(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """显式传了语言方向就以传入值为准，识别不覆盖。"""
    rel = _write_scratch("lang-explicit", {"explicit.csv": _ecdict_csv_bytes_many()})

    resp = await client.post(
        "/api/admin/dictionaries/import-from-dicts-dir",
        headers=admin_headers,
        json={
            "name": "Explicit Lang",
            "format": "ecdict",
            "lang_from": "en",
            "lang_to": "zh-Hant",
            "files": [f"{rel}/explicit.csv"],
        },
    )
    assert resp.status_code == 200, resp.text
    task = await wait_for_task(client, admin_headers, resp.json()["task_id"])
    assert task["status"] == "success", task
    assert task["result"]["lang_from"] == "en"
    assert task["result"]["lang_to"] == "zh-Hant"


async def test_batch_import_imports_every_detected_dictionary(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """走一遍前端批量导入的实际路径：扫描目录 → 逐部串行导入 → 再扫描确认全部入库。"""
    files: dict[str, bytes] = dict(_build_stardict_bytes())
    files["dict_a.csv"] = _ecdict_csv_bytes_many(2)
    files["dict_b.csv"] = _ecdict_csv_bytes_many(2)
    rel = _write_scratch("batch", files)

    listing = await client.get(
        "/api/admin/dictionaries/dicts-dir-files", params={"path": rel}, headers=admin_headers
    )
    groups = [g for g in listing.json()["dictionaries"] if g["importable"]]
    assert len(groups) == 3

    for group in groups:
        resp = await client.post(
            "/api/admin/dictionaries/import-from-dicts-dir",
            headers=admin_headers,
            json={
                "name": group["name"],
                "format": group["format"],
                "files": [f["relpath"] for f in group["files"]],
            },
        )
        assert resp.status_code == 200, resp.text
        task = await wait_for_task(client, admin_headers, resp.json()["task_id"])
        assert task["status"] == "success", task

    listing = await client.get(
        "/api/admin/dictionaries/dicts-dir-files", params={"path": rel}, headers=admin_headers
    )
    assert len(listing.json()["dictionaries"]) == 3
    assert all(g["imported"] for g in listing.json()["dictionaries"])


def _build_mdict_with_resource_bytes(tmp_path: Path) -> dict[str, bytes]:
    """生成一个带 .mdd 资源的迷你 MDict，用于验证「不导入发音/图片」。"""
    from mdict_utils import writer

    src = tmp_path / "src"
    src.mkdir()
    (src / "words.txt").write_text(
        'apple\n<p>a fruit <img src="pic/apple.png"></p>\n</>\n', encoding="utf-8"
    )
    res = tmp_path / "mdd_src"
    (res / "pic").mkdir(parents=True)
    (res / "pic" / "apple.png").write_bytes(b"\x89PNG-fake-content")

    mdx = tmp_path / "mini.mdx"
    writer.pack(
        str(mdx),
        writer.pack_mdx_txt(str(src / "words.txt"), encoding="utf-8"),
        title="Mini",
        description="",
        encoding="utf-8",
    )
    mdd = tmp_path / "mini.mdd"
    writer.pack(str(mdd), writer.pack_mdd_file(str(res)), title="Mini", description="", is_mdd=True)
    return {"mini.mdx": mdx.read_bytes(), "mini.mdd": mdd.read_bytes()}


async def test_import_from_dicts_dir_can_skip_resources(
    client: AsyncClient, admin_headers: dict[str, str], tmp_path: Path
) -> None:
    """勾「不导入发音/图片」时只写释义，不在磁盘上再解包一份 .mdd。

    大词典的 .mdd 常有几个 GB，解包一份等于再占一份磁盘；语义上也要保证引用不被改写
    （改了只会指向不存在的文件）。
    """
    files = _build_mdict_with_resource_bytes(tmp_path)
    settings = get_settings()
    storage = Path(settings.dictionary_storage_path)

    rel = _write_scratch("skip-res", files)
    resp = await client.post(
        "/api/admin/dictionaries/import-from-dicts-dir",
        headers=admin_headers,
        json={
            "name": "Skip Resources",
            "format": "mdict",
            "lang_from": "en",
            "lang_to": "zh-Hans",
            "skip_resources": True,
            "files": [f"{rel}/{name}" for name in files],
        },
    )
    assert resp.status_code == 200, resp.text
    task = await wait_for_task(client, admin_headers, resp.json()["task_id"])
    assert task["status"] == "success", task
    skipped_id = task["result"]["dictionary_id"]

    # 磁盘上没有解包出来的资源
    assert not (storage / str(skipped_id) / "res").exists()
    # 源文件仍在原处：本应用不会删用户放在 /data/dicts 的文件
    assert (Path(settings.dicts_inbox_path) / rel / "mini.mdx").exists()

    # 释义照常入库，且引用保持原样未被改写成 /dict-res/
    resp = await client.get(
        f"/api/admin/dictionaries/{skipped_id}/test-query",
        params={"word": "apple"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    definition = resp.json()[0]["definition"]
    assert "a fruit" in definition
    assert 'src="pic/apple.png"' in definition
    assert "/dict-res/" not in definition

    # 对照组：不带该字段时资源照常解包
    rel_kept = _write_scratch("with-res", files)
    resp = await client.post(
        "/api/admin/dictionaries/import-from-dicts-dir",
        headers=admin_headers,
        json={
            "name": "With Resources",
            "format": "mdict",
            "lang_from": "en",
            "lang_to": "zh-Hans",
            "files": [f"{rel_kept}/{name}" for name in files],
        },
    )
    assert resp.status_code == 200, resp.text
    task = await wait_for_task(client, admin_headers, resp.json()["task_id"])
    assert task["status"] == "success", task
    kept_id = task["result"]["dictionary_id"]

    resource = storage / str(kept_id) / "res" / "pic" / "apple.png"
    assert resource.read_bytes() == b"\x89PNG-fake-content"


async def _import_three_dictionaries(
    client: AsyncClient, admin_headers: dict[str, str]
) -> list[int]:
    """批量启停的用例都要先有几部词典；导入后默认是 disabled。"""
    ids: list[int] = []
    for index in range(3):
        dictionary = await import_dictionary(
            client,
            admin_headers,
            data={
                "name": f"Batch Status {index}",
                "format": "ecdict",
                "lang_from": "en",
                "lang_to": "zh",
            },
            files={"files": ("batch.csv", _ecdict_csv_bytes(), "text/csv")},
        )
        assert dictionary["status"] == "disabled"
        ids.append(dictionary["id"])
    return ids


async def _statuses(client: AsyncClient, admin_headers: dict[str, str]) -> dict[int, str]:
    listing = await client.get("/api/admin/dictionaries", headers=admin_headers)
    return {d["id"]: d["status"] for d in listing.json()}


async def test_batch_enable_and_disable_dictionaries(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """一键批量启用/停用：一次请求改多部词典的状态，未选中的不受影响。"""
    ids = await _import_three_dictionaries(client, admin_headers)

    resp = await client.put(
        "/api/admin/dictionaries/batch-status",
        headers=admin_headers,
        json={"dictionary_ids": ids[:2], "status": "enabled"},
    )
    assert resp.status_code == 200, resp.text
    assert {d["id"]: d["status"] for d in resp.json()} == {
        ids[0]: "enabled",
        ids[1]: "enabled",
    }

    statuses = await _statuses(client, admin_headers)
    assert statuses[ids[0]] == "enabled"
    assert statuses[ids[1]] == "enabled"
    # 没勾选的第三部不受影响
    assert statuses[ids[2]] == "disabled"

    # 再一键全部停用
    resp = await client.put(
        "/api/admin/dictionaries/batch-status",
        headers=admin_headers,
        json={"dictionary_ids": ids, "status": "disabled"},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 3
    assert all(d["status"] == "disabled" for d in resp.json())
    statuses = await _statuses(client, admin_headers)
    assert all(statuses[dict_id] == "disabled" for dict_id in ids)


async def test_batch_status_dedupes_repeated_ids(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    ids = await _import_three_dictionaries(client, admin_headers)

    resp = await client.put(
        "/api/admin/dictionaries/batch-status",
        headers=admin_headers,
        json={"dictionary_ids": [ids[0], ids[0], ids[0]], "status": "enabled"},
    )
    assert resp.status_code == 200, resp.text
    # 同一个 ID 传三次只处理一次，不会重复写审计日志
    assert [d["id"] for d in resp.json()] == [ids[0]]
    assert (await _statuses(client, admin_headers))[ids[0]] == "enabled"


async def test_batch_status_rejects_unknown_status(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """status 只认 enabled/disabled，且校验要在动手改之前完成，不留半改状态。"""
    ids = await _import_three_dictionaries(client, admin_headers)

    resp = await client.put(
        "/api/admin/dictionaries/batch-status",
        headers=admin_headers,
        json={"dictionary_ids": ids, "status": "archived"},
    )
    assert resp.status_code == 422
    statuses = await _statuses(client, admin_headers)
    assert all(statuses[dict_id] == "disabled" for dict_id in ids)


async def test_batch_status_rejects_unknown_dictionary_id(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """只要有一个 ID 不存在就整批拒绝，避免留下"改了一半"的中间状态。"""
    ids = await _import_three_dictionaries(client, admin_headers)

    resp = await client.put(
        "/api/admin/dictionaries/batch-status",
        headers=admin_headers,
        json={"dictionary_ids": [ids[0], 99_999_999], "status": "enabled"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"
    # 已存在的那部也不能被改动
    assert (await _statuses(client, admin_headers))[ids[0]] == "disabled"


async def test_batch_status_rejects_empty_list(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.put(
        "/api/admin/dictionaries/batch-status",
        headers=admin_headers,
        json={"dictionary_ids": [], "status": "enabled"},
    )
    assert resp.status_code == 422


async def test_batch_status_requires_admin(client: AsyncClient) -> None:
    resp = await client.put(
        "/api/admin/dictionaries/batch-status",
        json={"dictionary_ids": [1], "status": "enabled"},
    )
    assert resp.status_code == 401


# --------------------------------------------------------------------- 批量重命名


async def _import_named_dictionary(
    client: AsyncClient, admin_headers: dict[str, str], name: str
) -> int:
    dictionary = await import_dictionary(
        client,
        admin_headers,
        data={"name": name, "format": "ecdict", "lang_from": "en", "lang_to": "zh"},
        files={"files": ("rename.csv", _ecdict_csv_bytes(), "text/csv")},
    )
    return dictionary["id"]


async def _names(client: AsyncClient, admin_headers: dict[str, str]) -> dict[int, str]:
    listing = await client.get("/api/admin/dictionaries", headers=admin_headers)
    return {d["id"]: d["name"] for d in listing.json()}


async def test_rename_preview_does_not_touch_names(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """dry_run 只回对照表：正则写错一次能改坏几十个名字，得先能看见结果再决定。"""
    first = await _import_named_dictionary(client, admin_headers, "[中]汉典")
    second = await _import_named_dictionary(client, admin_headers, "[日]大辞林")

    resp = await client.post(
        "/api/admin/dictionaries/rename",
        headers=admin_headers,
        json={
            "pattern": r"^\[[中英日]\]",
            "replacement": "",
            "dictionary_ids": [first, second],
            "dry_run": True,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applied"] is False
    assert {item["new_name"] for item in body["items"]} == {"汉典", "大辞林"}

    names = await _names(client, admin_headers)
    assert names[first] == "[中]汉典"


async def test_rename_applies_changes(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    dictionary_id = await _import_named_dictionary(client, admin_headers, "[英]牛津高阶")

    resp = await client.post(
        "/api/admin/dictionaries/rename",
        headers=admin_headers,
        json={
            "pattern": r"^\[英\]",
            "replacement": "",
            "dictionary_ids": [dictionary_id],
            "dry_run": False,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["applied"] is True
    assert (await _names(client, admin_headers))[dictionary_id] == "牛津高阶"


async def test_rename_supports_backreferences(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """替换串支持 \\1 这类反向引用，方便只保留捕获到的分组。"""
    dictionary_id = await _import_named_dictionary(client, admin_headers, "汉典（中华书局）")

    resp = await client.post(
        "/api/admin/dictionaries/rename",
        headers=admin_headers,
        json={
            "pattern": r"^(.+?)（.+）$",
            "replacement": r"\1",
            "dictionary_ids": [dictionary_id],
            "dry_run": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"][0]["new_name"] == "汉典"


async def test_rename_skips_names_that_would_become_empty(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """替换结果为空就跳过：留一个不可用的名字比不改更糟。"""
    dictionary_id = await _import_named_dictionary(client, admin_headers, "词库")

    resp = await client.post(
        "/api/admin/dictionaries/rename",
        headers=admin_headers,
        json={
            "pattern": "^.*$",
            "replacement": "",
            "dictionary_ids": [dictionary_id],
            "dry_run": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []


async def test_rename_rejects_invalid_pattern(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.post(
        "/api/admin/dictionaries/rename",
        headers=admin_headers,
        json={"pattern": "([", "replacement": "", "dry_run": True},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


async def test_rename_requires_admin(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/admin/dictionaries/rename",
        json={"pattern": "a", "replacement": "", "dry_run": True},
    )
    assert resp.status_code == 401


# ------------------------------------------- MDict 同级附属资源（CSS/字体/脚本）
#
# MDict 的惯例是把样式表、字体、脚本放在 .mdx 同级目录，词条里的 <link href="oxbw.css">
# 就指着它们（大辞泉、岩波、広辞苑、明镜、新世纪、Weblio 等 63 部全是这样，Weblio 甚至
# 没有 .mdd）。早先只解包 .mdd，这些文件全部 404，于是图标按原始像素渲染、表格丢边框。


async def test_import_from_dicts_dir_copies_sibling_resources(
    client: AsyncClient, admin_headers: dict[str, str], tmp_path: Path
) -> None:
    """导入时把 .mdx 同级的 CSS 一并复制进 res/，词典本体不进 res/。"""
    files = _build_mdict_with_resource_bytes(tmp_path)
    files["mini.css"] = b"img.audio{height:1em}"
    settings = get_settings()

    rel = _write_scratch("sibling-res", files)
    resp = await client.post(
        "/api/admin/dictionaries/import-from-dicts-dir",
        headers=admin_headers,
        json={
            "name": "Sibling Res",
            "format": "mdict",
            "lang_from": "en",
            "lang_to": "zh-Hans",
            "files": [f"{rel}/{name}" for name in files],
        },
    )
    assert resp.status_code == 200, resp.text
    task = await wait_for_task(client, admin_headers, resp.json()["task_id"])
    assert task["status"] == "success", task
    dict_id = task["result"]["dictionary_id"]

    res = Path(settings.dictionary_storage_path) / str(dict_id) / "res"
    # 同级 css 被复制过来（这正是图标尺寸与表格边框的来源）
    assert (res / "mini.css").read_bytes() == b"img.audio{height:1em}"
    # .mdd 照常解包
    assert (res / "pic" / "apple.png").exists()
    # 词典本体不进 res/：词条已入库、.mdd 已解包，复制本体只会白占几十 MB
    assert not (res / "mini.mdx").exists()
    assert not (res / "mini.mdd").exists()


async def test_upload_accepts_sibling_resources(
    client: AsyncClient, admin_headers: dict[str, str], tmp_path: Path
) -> None:
    """浏览器上传也允许带上配套的 CSS/字体：MDict 的白名单此前只收 .mdx/.mdd，
    上传的词典注定丢样式。伪装成词典仍不可行——解析阶段没有 .mdx 会直接报错。"""
    files = _build_mdict_with_resource_bytes(tmp_path)
    settings = get_settings()

    dictionary = await import_dictionary(
        client,
        admin_headers,
        data={
            "name": "Uploaded Sibling",
            "format": "mdict",
            "lang_from": "en",
            "lang_to": "zh-Hans",
        },
        files=[
            ("files", ("mini.mdx", files["mini.mdx"], "application/octet-stream")),
            ("files", ("mini.mdd", files["mini.mdd"], "application/octet-stream")),
            ("files", ("mini.css", b"img.audio{height:1em}", "text/css")),
        ],
    )

    storage = Path(settings.dictionary_storage_path) / str(dictionary["id"])
    assert (storage / "res" / "mini.css").read_bytes() == b"img.audio{height:1em}"
    # 上传的文件归档到本应用管理的 source/（repair-resources 的源目录就是它）
    assert (storage / "source" / "mini.css").exists()


async def test_repair_resources_backfills_existing_dictionary(
    client: AsyncClient, admin_headers: dict[str, str], tmp_path: Path
) -> None:
    """存量词典靠这个端点补文件——不必重新导入（大辞泉有 95 万词条，重导代价太大）。"""
    files = _build_mdict_with_resource_bytes(tmp_path)
    settings = get_settings()
    rel = _write_scratch("repair-res", files)

    dictionary = await import_from_dicts_dir(
        client,
        admin_headers,
        json={
            "name": "Repair Res",
            "format": "mdict",
            "lang_from": "en",
            "lang_to": "zh-Hans",
            "files": [f"{rel}/{name}" for name in files],
        },
    )
    res = Path(settings.dictionary_storage_path) / str(dictionary["id"]) / "res"
    # 模拟「修好之前导入的存量词典」：res/ 里没有同级 css
    assert not (res / "mini.css").exists()
    _write_scratch("repair-res", {"mini.css": b"img.audio{height:1em}"})

    resp = await client.post(
        "/api/admin/dictionaries/repair-resources",
        headers=admin_headers,
        json={"dictionary_ids": [dictionary["id"]]},
    )
    assert resp.status_code == 200, resp.text
    task = await wait_for_task(client, admin_headers, resp.json()["task_id"])
    assert task["status"] == "success", task
    assert task["result"] == {"dictionaries": 1, "files": 1}

    assert (res / "mini.css").read_bytes() == b"img.audio{height:1em}"

    # 再跑一次：文件已在，不重复计数（幂等）
    resp = await client.post(
        "/api/admin/dictionaries/repair-resources",
        headers=admin_headers,
        json={"dictionary_ids": [dictionary["id"]]},
    )
    task = await wait_for_task(client, admin_headers, resp.json()["task_id"])
    assert task["result"] == {"dictionaries": 0, "files": 0}


async def test_repair_resources_creates_res_dir_for_mdx_only_dictionary(
    client: AsyncClient, admin_headers: dict[str, str], tmp_path: Path
) -> None:
    """只有 .mdx 没有 .mdd 的词典也该补——它从来没有过 res/，但照样需要那个 css。

    第一版实现写的是「没有 res/ 就跳过，说明用户当初勾了 skip_resources」，把这一整类
    都误判掉了：Weblio類語辞典、moji辞書、thesaurus近反义词、搜韵诗词等 19 部全都只有
    .mdx，而它们的释义引用照常被改写成了 /dict-res/…，缺了 css 表格就看不出是表格。
    """
    files = _build_mdict_with_resource_bytes(tmp_path)
    settings = get_settings()
    # 只导入 .mdx：没有 .mdd 就没有资源可解包，导入时也不会建 res/
    rel = _write_scratch("repair-mdx-only", {"mini.mdx": files["mini.mdx"]})

    dictionary = await import_from_dicts_dir(
        client,
        admin_headers,
        json={
            "name": "Repair Mdx Only",
            "format": "mdict",
            "lang_from": "en",
            "lang_to": "zh-Hans",
            "files": [f"{rel}/mini.mdx"],
        },
    )
    res = Path(settings.dictionary_storage_path) / str(dictionary["id"]) / "res"
    assert not res.exists()
    # 同级 css 是这个词典本来就有的，只是早先的导入代码没复制它
    _write_scratch("repair-mdx-only", {"mini.css": b"table{border:1px solid}"})

    resp = await client.post(
        "/api/admin/dictionaries/repair-resources",
        headers=admin_headers,
        json={"dictionary_ids": [dictionary["id"]]},
    )
    task = await wait_for_task(client, admin_headers, resp.json()["task_id"])
    assert task["status"] == "success", task
    assert task["result"] == {"dictionaries": 1, "files": 1}
    assert (res / "mini.css").read_bytes() == b"table{border:1px solid}"


async def test_repair_resources_rejects_unknown_dictionary(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.post(
        "/api/admin/dictionaries/repair-resources",
        headers=admin_headers,
        json={"dictionary_ids": [999999]},
    )
    assert resp.status_code == 404


async def test_repair_resources_requires_admin(client: AsyncClient) -> None:
    resp = await client.post("/api/admin/dictionaries/repair-resources", json={})
    assert resp.status_code == 401
