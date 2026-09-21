"""语言路由的软过滤行为。

背景：`lang_from` 是导入时按采样自动识别的，并不可靠——实测用户的 63 部词典里有 6 部
中文词典被判成 en（含 46 万条的「汉典」）。原先查询用 `lang_from` **硬过滤**，判错就
等于那部词典的内容永远查不到。现在是「先按优先语言查，一部都没命中才退到其余语言」，
并且会把「这是兜底结果」透出来（`lang_match=false`）。

注意：整个测试会话共用同一个库，词典名与词条都在所有用例里可见，所以要保证每次
用到的名字和词都是唯一的，否则前一个用例建的词典会干扰后一个。
"""

import csv
import io
import itertools
import uuid

from httpx import AsyncClient

from app.services.settings_service import set_setting
from tests.conftest import import_dictionary

_counter = itertools.count(1)


def _zh_word() -> str:
    """每次生成一个唯一的中文词（用不会与别的用例重复的汉字串）。"""
    return f"路由词{next(_counter)}{uuid.uuid4().hex[:4]}"


def _other_word() -> str:
    return f"无关词{next(_counter)}{uuid.uuid4().hex[:4]}"


def _ecdict_csv(words: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["word", "translation"])
    writer.writeheader()
    for word in words:
        writer.writerow({"word": word, "translation": "释义内容"})
    return buf.getvalue().encode("utf-8")


async def _make_dict(
    client: AsyncClient,
    admin_headers: dict[str, str],
    name: str,
    lang_from: str,
    words: list[str],
) -> int:
    dictionary = await import_dictionary(
        client,
        admin_headers,
        data={"name": name, "format": "ecdict", "lang_from": lang_from, "lang_to": "zh-Hans"},
        files={"files": (f"{name}.csv", _ecdict_csv(words), "text/csv")},
    )
    resp = await client.put(
        f"/api/admin/dictionaries/{dictionary['id']}/enable", headers=admin_headers
    )
    assert resp.status_code == 200
    return dictionary["id"]


async def _names_for(
    client: AsyncClient, query: str, dict_ids: list[int] | None = None, **params
) -> dict[str, bool]:
    """返回本次命中里「本次涉及的词典」的名称 -> lang_match。"""
    resp = await client.get("/api/dict/search", params={"word": query, **params})
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    if dict_ids is not None:
        results = [item for item in results if item["dictionary_id"] in dict_ids]
    return {item["dictionary_name"]: item["lang_match"] for item in results}


async def test_preferred_language_hit_excludes_other_languages(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """优先语言命中时只返回优先语言，不把其他语言的无关结果混进来。"""
    word = _zh_word()
    zh_id = await _make_dict(client, admin_headers, "中文词典甲A", "zh-Hans", [word])
    en_id = await _make_dict(client, admin_headers, "英文词典乙A", "en", [word])
    set_setting(db_session, "open_access", "true")

    # 输入是中文 -> 优先语言是 zh*，只有那部 zh-Hans 词典算命中
    assert await _names_for(client, word, [zh_id, en_id]) == {"中文词典甲A": True}


async def test_falls_back_when_preferred_language_has_no_hit(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """优先语言一部都没命中时退到其余语言——这是「被误判成 en 的中文词典」仍可查的关键。"""
    word = _zh_word()
    # 中文词典里没有这个词，只有被误判成 en 的那部有
    zh_id = await _make_dict(client, admin_headers, "中文词典甲B", "zh-Hans", [_other_word()])
    en_id = await _make_dict(client, admin_headers, "被误判的词典B", "en", [word])
    set_setting(db_session, "open_access", "true")

    # 兜底结果要标出来，否则用户不知道这是「其他语言词典」给的
    assert await _names_for(client, word, [zh_id, en_id]) == {"被误判的词典B": False}


async def test_english_query_prefers_english_dictionaries(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    word = f"routingword{next(_counter)}{uuid.uuid4().hex[:4]}"
    zh_id = await _make_dict(client, admin_headers, "中文词典甲C", "zh-Hans", [word])
    en_id = await _make_dict(client, admin_headers, "英文词典乙C", "en", [word])
    set_setting(db_session, "open_access", "true")

    assert await _names_for(client, word, [zh_id, en_id]) == {"英文词典乙C": True}


async def test_fallback_respects_user_allowed_dictionaries(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """兜底候选同样不能绕过「可用词典」限制。"""
    word = _zh_word()
    allowed = await _make_dict(client, admin_headers, "中文词典甲D", "zh-Hans", [_other_word()])
    blocked = await _make_dict(client, admin_headers, "被误判的词典D", "en", [word])

    await client.post(
        "/api/auth/register", json={"username": "routinguserd", "password": "routingpass123"}
    )
    login = await client.post(
        "/api/auth/login", json={"username": "routinguserd", "password": "routingpass123"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = await client.put(
        "/api/auth/allowed-dictionaries", headers=headers, json={"dictionary_ids": [allowed]}
    )
    assert resp.status_code == 200

    body = await client.get("/api/dict/search", params={"word": word}, headers=headers)
    returned = {item["dictionary_id"] for item in body.json()["results"]}
    assert blocked not in returned


async def test_explicit_language_disables_fallback(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """显式指定语言方向时调用方已经说清楚要什么，不该再兜底。"""
    word = _zh_word()
    zh_id = await _make_dict(client, admin_headers, "中文词典甲E", "zh-Hans", [_other_word()])
    en_id = await _make_dict(client, admin_headers, "被误判的词典E", "en", [word])
    set_setting(db_session, "open_access", "true")

    assert await _names_for(client, word, [zh_id, en_id], **{"from": "zh-Hans"}) == {}


async def test_explicit_dict_selection_is_never_marked_as_fallback(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """显式点名某部词典时它就是要查的那部，不该被标成「其他语言词典」。"""
    word = _zh_word()
    await _make_dict(client, admin_headers, "中文词典甲F", "zh-Hans", [_other_word()])
    target = await _make_dict(client, admin_headers, "被误判的词典F", "en", [word])
    set_setting(db_session, "open_access", "true")

    resp = await client.get("/api/v1/query", params={"word": word, "dict": str(target)})
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert [item["dictionary_name"] for item in results] == ["被误判的词典F"]
    assert results[0]["lang_match"] is True


async def test_cache_does_not_swallow_the_fallback(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """缓存 key 用的是完整候选集，所以「优先语言没命中」这个空结果不会把兜底压掉。

    连查两次是为了走缓存分支；如果 key 只包含优先语言那批，第二次就会返回空。
    """
    word = _zh_word()
    zh_id = await _make_dict(client, admin_headers, "中文词典甲G", "zh-Hans", [_other_word()])
    en_id = await _make_dict(client, admin_headers, "被误判的词典G", "en", [word])
    set_setting(db_session, "open_access", "true")

    first = await _names_for(client, word, [zh_id, en_id])
    second = await _names_for(client, word, [zh_id, en_id])
    assert first == second == {"被误判的词典G": False}


# --------------------------------------------------- 重新识别（回溯修正已入库的值）
#
# 采样逻辑修好之后，**已入库的 lang_from 不会自动更新**；而查询路由按它过滤，所以必须
# 提供一个回溯修正的动作（CLI `redetect-languages` 调用下面这两个服务函数）。
# 实测：用户的「汉典」（46 万条）原先存的是 en，重新识别后是正确的 zh-Hans。


def _make_row(db_session, tmp_path, file_path: str, method: str = "dicts_dir"):
    from app.models.dictionary import Dictionary

    dictionary = Dictionary(
        name="重新识别用例",
        format="mdict",
        lang_from="en",
        lang_to="zh-Hans",
        file_path=file_path,
        import_method=method,
        status="disabled",
    )
    db_session.add(dictionary)
    db_session.commit()
    return dictionary


def test_source_paths_for_dicts_dir_splits_and_skips_missing(db_session, tmp_path) -> None:
    from app.services import dictionary_service

    mdx = tmp_path / "a.mdx"
    mdx.write_bytes(b"x")
    mdd = tmp_path / "a.mdd"
    mdd.write_bytes(b"y")
    missing = tmp_path / "gone.mdx"

    row = _make_row(db_session, tmp_path, f"{mdx}; {mdd}; {missing}")
    # 缺失的路径被跳过而不是抛错——目录是用户自己管的，文件可能已被清掉
    assert dictionary_service.source_paths_for(row) == [mdx, mdd]


def test_source_paths_for_upload_reads_archive_directory(db_session, tmp_path) -> None:
    from app.services import dictionary_service

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    mdx = source_dir / "a.mdx"
    mdx.write_bytes(b"x")
    mdd = source_dir / "a.mdd"
    mdd.write_bytes(b"y")

    # upload 方式存的是归档目录（文件被移进去、名字不变），不是分号分隔的路径列表。
    # 顺序无意义（各解析器按后缀自己挑），所以按集合比。
    row = _make_row(db_session, tmp_path, str(source_dir), method="upload")
    assert set(dictionary_service.source_paths_for(row)) == {mdx, mdd}


def test_apply_detected_language_only_overwrites_detected_sides(db_session, tmp_path) -> None:
    from app.services import dictionary_service

    row = _make_row(db_session, tmp_path, str(tmp_path / "none.mdx"))

    # 只识别出词头侧时，不能把 lang_to 一起改掉
    assert dictionary_service.apply_detected_language(db_session, row, "zh-Hans", None) is True
    assert row.lang_from == "zh-Hans"
    assert row.lang_to == "zh-Hans"

    # 再跑一次同样的结果不该产生写入（幂等）
    assert dictionary_service.apply_detected_language(db_session, row, "zh-Hans", None) is False


def test_apply_detected_language_ignores_all_none(db_session, tmp_path) -> None:
    from app.services import dictionary_service

    row = _make_row(db_session, tmp_path, str(tmp_path / "none.mdx"))
    assert dictionary_service.apply_detected_language(db_session, row, None, None) is False
    assert row.lang_from == "en"


# ------------------------------------------------------- 检索范围（会话级筛选）
#
# 侧边栏勾选只影响当前浏览器这一次检索，通过已有的 dict= 参数传给后端：不写库、不影响
# 其他用户与 Token。前端侧没有测试框架，所以这里覆盖参数本身的语义。


async def test_web_search_accepts_dictionary_scope(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    word = _zh_word()
    first = await _make_dict(client, admin_headers, "范围词典甲", "zh-Hans", [word])
    second = await _make_dict(client, admin_headers, "范围词典乙", "zh-Hans", [word])
    set_setting(db_session, "open_access", "true")

    both = await client.get("/api/dict/search", params={"word": word})
    hit = {item["dictionary_id"] for item in both.json()["results"]} & {first, second}
    assert hit == {first, second}

    only_first = await client.get("/api/dict/search", params={"word": word, "dict": str(first)})
    hit = {item["dictionary_id"] for item in only_first.json()["results"]} & {first, second}
    assert hit == {first}


async def test_web_search_scope_cannot_bypass_user_limits(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """dict= 只能收窄范围，不能用来查自己没被授权的词典。"""
    word = _zh_word()
    allowed = await _make_dict(client, admin_headers, "范围词典丙", "zh-Hans", [_other_word()])
    blocked = await _make_dict(client, admin_headers, "范围词典丁", "zh-Hans", [word])

    await client.post(
        "/api/auth/register", json={"username": "scopeuser", "password": "scopepass123"}
    )
    login = await client.post(
        "/api/auth/login", json={"username": "scopeuser", "password": "scopepass123"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = await client.put(
        "/api/auth/allowed-dictionaries", headers=headers, json={"dictionary_ids": [allowed]}
    )
    assert resp.status_code == 200

    scoped = await client.get(
        "/api/dict/search", params={"word": word, "dict": str(blocked)}, headers=headers
    )
    assert blocked not in {item["dictionary_id"] for item in scoped.json()["results"]}


async def test_web_search_ignores_invalid_dict_values(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """非法/失效的 dict 值被忽略、退化成不限制，而不是让整条查询失败。"""
    word = _zh_word()
    made = await _make_dict(client, admin_headers, "范围词典戊", "zh-Hans", [word])
    set_setting(db_session, "open_access", "true")

    resp = await client.get("/api/dict/search", params={"word": word, "dict": "abc,,"})
    assert resp.status_code == 200, resp.text
    assert made in {item["dictionary_id"] for item in resp.json()["results"]}
