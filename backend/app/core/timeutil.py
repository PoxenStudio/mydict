"""日期与时区：全项目「一天」的唯一出处。

时间戳一律以 **UTC（naive）** 存库——`server_default=func.now()` 在 SQLite 上就是
`CURRENT_TIMESTAMP`（UTC），Python 侧的写入也都用 `datetime.now(timezone.utc)`。而「一天」要按
**部署本地时区**划分：管理员看的是本地日历日，统计页的日期选择器给的也是本地日期。

两者口径不同，所以任何「按天」的过滤都必须先在这里换算出该本地日对应的 UTC 区间，**绝不能拿本地
日期去和 `func.date(created_at)` 比**——那会在本地 00:00 到与 UTC 的偏移量之间整整错开一天
（UTC+8 部署下就是每天凌晨 8 小时统计全为 0）。改用区间比较还有个附带好处：能走
`ix_query_logs_created_at` 索引，`func.date(col)` 会让索引失效。
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
    """本地日 `target` 对应的 `[起, 止)` UTC 区间，返回 **naive UTC** datetime。

    返回 naive 值是有意的：数据库列本身就是 naive 的，而 SQLAlchemy 在 SQLite 上会把 bind 参数的
    tzinfo 直接丢掉，传 aware 值反而会让偏移量算错。所以这里先换算成 UTC 再去掉 tzinfo。

    区间取半开（止于次日零点、不含），相邻两天既不重复计数也不会在微秒边界漏记录。
    """
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
    """到下一个本地零点的秒数，用于按日限流的 `Retry-After`。

    按日限流的计数器是以本地日期为键的（见 rate_limit_service），所以在本地零点重置；这里必须
    同样按本地零点计算，否则返回的等待时间会多算一个时区偏移。
    """
    zone = local_zone()
    now = datetime.now(zone)
    tomorrow = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=zone)
    return max(1, int((tomorrow - now).total_seconds()))
