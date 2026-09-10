"""查询结果 TTL 缓存：Key 为 word_lower + 参与匹配的词典 id 集合，减少高频重复查询的 DB 读取。

词典启用/禁用/导入/删除时调用 invalidate() 整体清空（简单可靠；本项目数据规模下
全量失效的代价可忽略，不做按词典粒度的精细失效）。
"""

from threading import Lock

from cachetools import TTLCache

_TTL_SECONDS = 300
_cache: TTLCache = TTLCache(maxsize=10_000, ttl=_TTL_SECONDS)
_lock = Lock()


def make_key(word_lower: str, dictionary_ids: tuple[int, ...]) -> str:
    return f"{word_lower}|{','.join(str(i) for i in sorted(dictionary_ids))}"


def get(key: str):
    with _lock:
        return _cache.get(key)


def set(key: str, value) -> None:  # noqa: A001 - 与 dict-like 缓存接口保持一致命名
    with _lock:
        _cache[key] = value


def invalidate() -> None:
    with _lock:
        _cache.clear()
