"""匿名请求（无 Token/未登录）按 IP 的每分钟限流：进程内内存计数器。

Token 每日限流走数据库（见 services/rate_limit_service.py）：按日计数天然需要跨进程
重启保留，直接以 DB 行作为计数器比再维护一份内存态更简单可靠；这里的按分钟计数器
窗口很短，重启丢失可以接受，用内存 TTLCache 已经足够。
"""

import time
from threading import Lock

from cachetools import TTLCache

_counters: TTLCache = TTLCache(maxsize=100_000, ttl=70)
_lock = Lock()


def check_and_increment(ip: str, limit_per_min: int) -> bool:
    """返回 True 表示放行，False 表示本分钟已超限。"""
    minute_bucket = int(time.time() // 60)
    key = f"{ip}:{minute_bucket}"
    with _lock:
        count = _counters.get(key, 0) + 1
        _counters[key] = count
    return count <= limit_per_min


def seconds_to_next_minute() -> int:
    return 60 - int(time.time() % 60)


def reset() -> None:
    """清空计数器，仅供测试使用。"""
    with _lock:
        _counters.clear()
