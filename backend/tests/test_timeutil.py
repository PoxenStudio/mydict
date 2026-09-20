from datetime import date, datetime, timedelta

from app.core import timeutil
from app.core.config import get_settings


def test_day_bounds_utc_returns_naive_utc_and_spans_exactly_one_local_day() -> None:
    """边界必须是 naive UTC：数据库列是 naive 的，SQLAlchemy 在 SQLite 上会丢掉 tzinfo。"""
    start, end = timeutil.day_bounds_utc(date(2026, 3, 5))

    assert start.tzinfo is None
    assert end.tzinfo is None
    assert end - start == timedelta(days=1)


def test_consecutive_days_are_contiguous() -> None:
    """半开区间：前一天的止 == 后一天的起，相邻两天既不重叠也不留缝。"""
    _, first_end = timeutil.day_bounds_utc(date(2026, 3, 5))
    second_start, _ = timeutil.day_bounds_utc(date(2026, 3, 6))

    assert first_end == second_start


def test_range_bounds_utc_covers_inclusive_day_range() -> None:
    start, end = timeutil.range_bounds_utc(date(2026, 3, 1), date(2026, 3, 3))

    # 含首含尾共三天
    assert end - start == timedelta(days=3)


def test_explicit_timezone_decouples_bounds_from_system_timezone(monkeypatch) -> None:
    """配置了 timezone 就按它算，与宿主机/容器自身的时区无关。"""
    settings = get_settings()

    monkeypatch.setattr(settings, "timezone", "Asia/Shanghai")
    start_shanghai, _ = timeutil.day_bounds_utc(date(2026, 3, 5))

    monkeypatch.setattr(settings, "timezone", "UTC")
    start_utc, _ = timeutil.day_bounds_utc(date(2026, 3, 5))

    # 同一个本地日，UTC 下的起点比 Asia/Shanghai 下的起点晚 8 小时
    assert start_utc - start_shanghai == timedelta(hours=8)
    # Asia/Shanghai 的 2026-03-05 00:00 就是 UTC 的 2026-03-04 16:00
    assert start_shanghai == datetime(2026, 3, 4, 16, 0)


def test_empty_timezone_follows_system_local_zone() -> None:
    """留空时跟随容器/宿主机本地时区——用 UTC 偏移量比对，tzinfo 对象每次都是新实例，不能用 is。"""
    assert timeutil.now_local().utcoffset() == datetime.now().astimezone().utcoffset()


def test_today_and_day_str_follow_local_calendar() -> None:
    local_date = timeutil.now_local().date()

    assert timeutil.today_str() == local_date.isoformat()
    assert timeutil.day_str(-1) == (local_date - timedelta(days=1)).isoformat()
    assert timeutil.day_str(6) == (local_date + timedelta(days=6)).isoformat()


def test_seconds_to_local_midnight_is_within_one_day() -> None:
    seconds = timeutil.seconds_to_local_midnight()

    assert 0 < seconds <= 24 * 60 * 60


def test_invalid_timezone_falls_back_to_system_zone(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "timezone", "Not/AZone")

    assert timeutil.now_local().utcoffset() == datetime.now().astimezone().utcoffset()
