import csv
import io
import struct

from httpx import AsyncClient

from app.core.config import get_settings


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
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
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
    dict_id = dictionary["id"]

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


async def test_import_from_dicts_dir_moves_source_files(
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
    names = {f["name"] for f in resp.json()}
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

    # 成功导入后源文件应从 /data/dicts 移走
    assert not os.path.exists(os.path.join(inbox, "greeting.ifo"))
    source_dir = os.path.join(settings.dictionary_storage_path, str(dictionary["id"]), "source")
    assert os.path.exists(os.path.join(source_dir, "greeting.ifo"))


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
