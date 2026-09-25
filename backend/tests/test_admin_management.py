from datetime import date, datetime, timedelta, timezone

from httpx import AsyncClient

from app.models.audit import AuditLog
from app.models.token import ApiToken
from app.models.query import QueryLog, QueryStatsDaily
from app.services.settings_service import set_setting
from app.tasks.stats_aggregation import aggregate_date
from app.core.timeutil import today_str
from tests.conftest import import_dictionary


async def test_token_lifecycle(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    resp = await client.post(
        "/api/admin/tokens",
        json={"name": "第三方插件", "daily_limit": 500},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    created = resp.json()
    assert created["token"].startswith("sk-")
    assert created["token_prefix"] == created["token"][:9] + "****"
    assert created["daily_limit"] == 500
    assert created["status"] == "active"
    token_id = created["id"]

    resp = await client.get("/api/admin/tokens", headers=admin_headers)
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()}
    assert "第三方插件" in names
    # 明文 Token 不应出现在列表接口
    assert all("token" not in t for t in resp.json())

    resp = await client.put(f"/api/admin/tokens/{token_id}/disable", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"

    resp = await client.put(f"/api/admin/tokens/{token_id}/enable", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    resp = await client.get(f"/api/admin/tokens/{token_id}/vocab-count", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == {"count": 0}

    resp = await client.post(f"/api/admin/tokens/{token_id}/regenerate", headers=admin_headers)
    assert resp.status_code == 200
    regenerated = resp.json()
    assert regenerated["token"] != created["token"]
    assert regenerated["id"] == token_id

    # 审计日志应记录创建/禁用/启用/重新生成
    db = _fresh_session()
    try:
        actions = {
            a.action for a in db.query(AuditLog).filter(AuditLog.target == str(token_id)).all()
        }
        assert {"token.create", "token.disabled", "token.active", "token.regenerate"} <= actions
    finally:
        db.close()


async def test_token_not_found(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    resp = await client.put("/api/admin/tokens/999999/disable", headers=admin_headers)
    assert resp.status_code == 404


async def test_admin_create_user(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    resp = await client.post(
        "/api/admin/users",
        json={"username": "createduser", "email": "created@example.com"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["username"] == "createduser"
    assert body["user"]["email"] == "created@example.com"
    assert body["user"]["status"] == "active"
    temp_password = body["temporary_password"]
    assert len(temp_password) >= 8

    # 临时密码应能直接登录
    resp = await client.post(
        "/api/auth/login", json={"username": "createduser", "password": temp_password}
    )
    assert resp.status_code == 200

    # 用户名重复应拒绝
    resp = await client.post(
        "/api/admin/users", json={"username": "createduser"}, headers=admin_headers
    )
    assert resp.status_code == 409


async def test_user_management_lifecycle(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await client.post(
        "/api/auth/register", json={"username": "manageduser", "password": "managedpass123"}
    )
    resp = await client.get(
        "/api/admin/users", params={"search": "manageduser"}, headers=admin_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    user_row = body["items"][0]
    assert user_row["username"] == "manageduser"
    user_id = user_row["id"]

    resp = await client.get(f"/api/admin/users/{user_id}", headers=admin_headers)
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["user"]["username"] == "manageduser"
    assert detail["vocab_items"] == []
    assert detail["recent_queries"] == []

    resp = await client.put(f"/api/admin/users/{user_id}/disable", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"

    # 被禁用用户登录应失败
    resp = await client.post(
        "/api/auth/login", json={"username": "manageduser", "password": "managedpass123"}
    )
    assert resp.status_code == 403

    resp = await client.put(f"/api/admin/users/{user_id}/enable", headers=admin_headers)
    assert resp.status_code == 200

    resp = await client.post(f"/api/admin/users/{user_id}/reset-password", headers=admin_headers)
    assert resp.status_code == 200
    temp_password = resp.json()["temporary_password"]
    assert len(temp_password) >= 8

    resp = await client.post(
        "/api/auth/login", json={"username": "manageduser", "password": temp_password}
    )
    assert resp.status_code == 200


async def test_settings_get_and_partial_update(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.get("/api/admin/settings", headers=admin_headers)
    assert resp.status_code == 200
    original = resp.json()
    assert original["site_name"] == "MyDict"
    assert original["vocab_max_items_per_owner"] is None
    assert original["search_hint_text"] == "小搜一下, 大进一步"

    resp = await client.put(
        "/api/admin/settings", json={"site_name": "我的词典"}, headers=admin_headers
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["site_name"] == "我的词典"
    # 未传的字段不应被覆盖
    assert updated["open_access"] == original["open_access"]
    assert updated["token_default_daily_limit"] == original["token_default_daily_limit"]

    resp = await client.put(
        "/api/admin/settings", json={"vocab_max_items_per_owner": 50}, headers=admin_headers
    )
    assert resp.json()["vocab_max_items_per_owner"] == 50

    # 显式传 null 应能清空回「不限」
    resp = await client.put(
        "/api/admin/settings", json={"vocab_max_items_per_owner": None}, headers=admin_headers
    )
    assert resp.json()["vocab_max_items_per_owner"] is None

    resp = await client.put(
        "/api/admin/settings", json={"site_name": "MyDict"}, headers=admin_headers
    )
    assert resp.json()["site_name"] == "MyDict"

    resp = await client.put(
        "/api/admin/settings", json={"search_hint_text": "欢迎回来"}, headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["search_hint_text"] == "欢迎回来"

    resp = await client.get("/api/public/settings")
    assert resp.json()["search_hint_text"] == "欢迎回来"

    # 超过 100 字上限拒绝
    resp = await client.put(
        "/api/admin/settings", json={"search_hint_text": "长" * 101}, headers=admin_headers
    )
    assert resp.status_code == 422

    resp = await client.put(
        "/api/admin/settings",
        json={"search_hint_text": "小搜一下, 大进一步"},
        headers=admin_headers,
    )
    assert resp.json()["search_hint_text"] == "小搜一下, 大进一步"


async def test_stats_overview_top_words_and_csv_export(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    import csv
    import io

    set_setting(db_session, "open_access", "true")
    dictionary = await import_dictionary(
        client,
        admin_headers,
        data={"name": "STATS-DICT", "format": "ecdict", "lang_from": "en", "lang_to": "zh"},
        files={
            "files": (
                "stats.csv",
                (
                    "word,phonetic,definition,translation,pos,collins,oxford,tag,bnc,frq,"
                    "exchange,detail,audio\nstatword,,,统计词,,,,,,,,,\n"
                ).encode("utf-8"),
                "text/csv",
            )
        },
    )
    dict_id = dictionary["id"]
    await client.put(f"/api/admin/dictionaries/{dict_id}/enable", headers=admin_headers)

    for _ in range(3):
        await client.get("/api/v1/query", params={"word": "statword"})

    resp = await client.get("/api/admin/stats/overview", headers=admin_headers)
    assert resp.status_code == 200
    overview = resp.json()
    # 直接数 query_logs，无需等定时聚合任务跑过也应立即反映刚才的 3 次查询
    assert overview["today_query_count"] >= 3
    assert overview["dictionary_count"] >= 1

    resp = await client.get(
        "/api/admin/stats/top-words", params={"limit": 5}, headers=admin_headers
    )
    assert resp.status_code == 200
    words = {row["word"] for row in resp.json()}
    assert "statword" in words

    resp = await client.get(
        "/api/admin/stats", params={"dimension": "source"}, headers=admin_headers
    )
    assert resp.status_code == 200
    sources = {row["label"] for row in resp.json()}
    assert "api" in sources

    resp = await client.get(
        "/api/admin/stats",
        params={"dimension": "source", "export": "csv"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert any(r["label"] == "api" for r in rows)

    resp = await client.get(
        "/api/admin/stats", params={"dimension": "notadimension"}, headers=admin_headers
    )
    assert resp.status_code == 422


async def test_stats_aggregation_populates_user_and_anonymous_rows(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    set_setting(db_session, "open_access", "true")
    dictionary = await import_dictionary(
        client,
        admin_headers,
        data={"name": "AGG-DICT", "format": "ecdict", "lang_from": "en", "lang_to": "zh"},
        files={
            "files": (
                "agg.csv",
                (
                    "word,phonetic,definition,translation,pos,collins,oxford,tag,bnc,frq,"
                    "exchange,detail,audio\naggword,,,聚合词,,,,,,,,,\n"
                ).encode("utf-8"),
                "text/csv",
            )
        },
    )
    dict_id = dictionary["id"]
    await client.put(f"/api/admin/dictionaries/{dict_id}/enable", headers=admin_headers)

    await client.post("/api/auth/register", json={"username": "agguser", "password": "aggpass123"})
    login = await client.post(
        "/api/auth/login", json={"username": "agguser", "password": "aggpass123"}
    )
    user_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    await client.get("/api/dict/search", params={"word": "aggword"}, headers=user_headers)
    await client.get("/api/dict/search", params={"word": "aggword"})  # 匿名

    today = date.today().isoformat()
    aggregate_date(today)

    me = await client.get("/api/auth/me", headers=user_headers)
    user_id = me.json()["id"]

    user_row = (
        db_session.query(QueryStatsDaily)
        .filter(QueryStatsDaily.stat_date == today, QueryStatsDaily.user_id == user_id)
        .first()
    )
    assert user_row is not None
    assert user_row.query_count >= 1

    anon_row = (
        db_session.query(QueryStatsDaily)
        .filter(
            QueryStatsDaily.stat_date == today,
            QueryStatsDaily.token_id.is_(None),
            QueryStatsDaily.user_id.is_(None),
        )
        .first()
    )
    assert anon_row is not None
    assert anon_row.query_count >= 1


def _local_moment_as_naive_utc(day_offset: int, hour: int, minute: int) -> datetime:
    """构造「本地某天的某时刻」对应的 naive UTC 瞬时。

    query_logs.created_at 存的就是 naive UTC，所以测试要自己把「本地时刻」换算过去才能精确控制
    一条日志落在哪一天。
    """
    local_zone = datetime.now().astimezone().tzinfo
    local_midnight = datetime.now(local_zone).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + timedelta(days=day_offset)
    return (
        (local_midnight + timedelta(hours=hour, minutes=minute))
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )


def _local_day(day_offset: int = 0) -> str:
    local_zone = datetime.now().astimezone().tzinfo
    return (datetime.now(local_zone) + timedelta(days=day_offset)).date().isoformat()


async def test_stats_overview_counts_local_day_boundary(
    client: AsyncClient, admin_headers: dict[str, str], db_session
) -> None:
    """统计里的「今天」必须按部署本地时区划分，不能拿本地日期去比 UTC 日。

    这里刻意用「本地今天 00:30」构造样本——它的 UTC 日属于**前一天**，因此只按 UTC 日比较的实现
    必然漏掉它。这样构造与测试运行时刻无关，不会出现「只在凌晨跑才失败」的假回归测试。
    """
    resp = await client.get("/api/admin/stats/overview", headers=admin_headers)
    assert resp.status_code == 200
    baseline = resp.json()["today_query_count"]

    # 本地今天 00:30：UTC 日 = 本地昨天，旧实现按 func.date(created_at) 比会漏掉
    db_session.add(
        QueryLog(
            source="api",
            word="boundary-inside",
            status="ok",
            created_at=_local_moment_as_naive_utc(0, 0, 30),
        )
    )
    db_session.commit()
    resp = await client.get("/api/admin/stats/overview", headers=admin_headers)
    assert resp.json()["today_query_count"] == baseline + 1, "本地当天 00:30 的查询必须计入「今天」"

    # 本地今天零点前 1 分钟：属于昨天，不能计入（守住半开区间）
    db_session.add(
        QueryLog(
            source="api",
            word="boundary-before",
            status="ok",
            created_at=_local_moment_as_naive_utc(0, 0, 0) - timedelta(minutes=1),
        )
    )
    db_session.commit()
    resp = await client.get("/api/admin/stats/overview", headers=admin_headers)
    assert (
        resp.json()["today_query_count"] == baseline + 1
    ), "本地零点前 1 分钟的查询不能计入「今天」"


def test_stats_aggregation_counts_local_day_boundary(db_session) -> None:
    """聚合任务要按「本地日」分组，否则行的标签（本地日期）与内容（UTC 日）会错位一个时区偏移。

    这里取一个**过去的本地日**（3 天前）来隔离：其他用例只会写「今天」的聚合行，用过去的日子
    可以确定这个断言不受它们影响。
    """
    target_day = _local_day(-3)
    db_session.add(
        QueryLog(
            source="web",
            word="agg-boundary",
            status="ok",
            # 该本地日的 00:30，其 UTC 日属于前一天
            created_at=_local_moment_as_naive_utc(-3, 0, 30),
        )
    )
    db_session.commit()

    aggregate_date(target_day)

    db_session.expire_all()
    anon_row = (
        db_session.query(QueryStatsDaily)
        .filter(
            QueryStatsDaily.stat_date == target_day,
            QueryStatsDaily.token_id.is_(None),
            QueryStatsDaily.user_id.is_(None),
        )
        .first()
    )
    assert anon_row is not None, "聚合任务应为该本地日写入匿名维度行"
    assert anon_row.query_count >= 1, "落在该本地日 00:30 的查询必须被聚合进这一天"


def _fresh_session():
    from app.core.db import SessionLocal

    return SessionLocal()


async def test_stats_invalid_date_returns_empty(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    for path, params in (
        ("/api/admin/stats", {"dimension": "date", "start_date": "abc"}),
        ("/api/admin/stats", {"dimension": "source", "end_date": "2026-13-40"}),
        ("/api/admin/stats/top-words", {"start_date": "bad"}),
    ):
        response = await client.get(path, params=params, headers=admin_headers)
        assert response.status_code == 200
        assert response.json() == []


async def test_token_delete_anonymizes_history(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """删除 Token：生词本级联清理，查询日志/统计保留但匿名化（token_id 置 NULL）。

    query_logs / query_stats_daily 对 api_tokens 的外键没有 ondelete（加它需要迁移），
    直接删会撞外键——这也是「Token 删不掉」的根源之一：此前根本没有删除功能。
    """
    resp = await client.post(
        "/api/admin/tokens", json={"name": "待删Token"}, headers=admin_headers
    )
    token_id = resp.json()["id"]

    # 造一条带 token 的查询日志与一条统计，证明删除不会连带丢运营数据
    from app.core.db import SessionLocal
    from app.models.query import QueryLog, QueryStatsDaily
    from app.models.vocab import TokenVocabItem

    db = SessionLocal()
    try:
        db.add(QueryLog(token_id=token_id, word="x", status="ok", source="api"))
        db.add(QueryStatsDaily(stat_date=today_str(), token_id=token_id, query_count=3))
        db.add(TokenVocabItem(token_id=token_id, word="apple"))
        db.commit()
    finally:
        db.close()

    resp = await client.delete(f"/api/admin/tokens/{token_id}", headers=admin_headers)
    assert resp.status_code == 204, resp.text

    db = SessionLocal()
    try:
        assert db.get(ApiToken, token_id) is None
        # 生词本随外键级联清理
        assert (
            db.query(TokenVocabItem).filter(TokenVocabItem.token_id == token_id).count() == 0
        )
        # 查询日志与统计保留，token_id 匿名化为 NULL
        log = db.query(QueryLog).filter(QueryLog.word == "x").one()
        assert log.token_id is None
        stat = (
            db.query(QueryStatsDaily)
            .filter(QueryStatsDaily.stat_date == today_str(), QueryStatsDaily.query_count == 3)
            .one()
        )
        assert stat.token_id is None
        # 审计日志
        actions = {
            a.action for a in db.query(AuditLog).filter(AuditLog.target == str(token_id)).all()
        }
        assert "token.delete" in actions
    finally:
        db.close()

    # 删过之后再删 → 404
    resp = await client.delete(f"/api/admin/tokens/{token_id}", headers=admin_headers)
    assert resp.status_code == 404


async def test_token_delete_requires_admin(client: AsyncClient) -> None:
    resp = await client.delete("/api/admin/tokens/1")
    assert resp.status_code == 401
