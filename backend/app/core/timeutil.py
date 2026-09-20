"""日期与时区：全项目「一天」的唯一出处。

时间戳一律以 naive UTC 存库，「一天」按部署本地时区划分。按天过滤必须先在这里把本地日换算成
UTC 半开区间再比较，不能拿本地日期去比 `func.date(created_at)`。
"""

import logging
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _system_zone():
    return datetime.now().astimezone().tzinfo


@lru_cache(maxsize=None)
def _resolve_zone(name: str):
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            logger.warning("TIMEZONE=%r 无效，回落到系统时区", name)
    return _system_zone()


def local_zone():
    """部署本地时区：配置了有效的 `settings.timezone` 就用它，否则用系统时区。

    系统时区只是当前时刻的固定偏移，没有夏令时规则；有夏令时的地区请显式配置 TIMEZONE。
    """
    return _resolve_zone((get_settings().timezone or "").strip())


def now_local() -> datetime:
    return datetime.now(local_zone())


def today() -> date:
    return now_local().date()


def day(offset_days: int = 0) -> date:
    """相对今天偏移若干天的本地日期。"""
    return today() + timedelta(days=offset_days)


def today_str() -> str:
    return today().isoformat()


def day_str(offset_days: int = 0) -> str:
    return day(offset_days).isoformat()


def parse_day(value: str | None) -> date | None:
    """解析 ISO 日期字符串；空值或格式非法返回 None。"""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def day_bounds_utc(target: date) -> tuple[datetime, datetime]:
    """本地日 `target` 对应的 `[起, 止)` UTC 区间，返回 naive UTC。"""
    zone = local_zone()
    start = datetime.combine(target, time.min, tzinfo=zone)
    end = datetime.combine(target + timedelta(days=1), time.min, tzinfo=zone)
    return (
        start.astimezone(timezone.utc).replace(tzinfo=None),
        end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def range_bounds_utc(start_day: date, end_day: date) -> tuple[datetime, datetime]:
    """本地日闭区间 `[start_day, end_day]` 对应的 `[起, 止)` UTC 区间。"""
    start, _ = day_bounds_utc(start_day)
    _, end = day_bounds_utc(end_day)
    return start, end


def seconds_to_local_midnight() -> int:
    """到下一个本地零点的秒数，用于按日限流的 `Retry-After`。"""
    zone = local_zone()
    now = datetime.now(zone)
    tomorrow = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=zone)
    return max(1, int((tomorrow - now).total_seconds()))
