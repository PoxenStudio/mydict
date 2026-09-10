from app.core import query_cache


def test_make_key_is_order_independent_for_dictionary_ids() -> None:
    assert query_cache.make_key("hello", (2, 1)) == query_cache.make_key("hello", (1, 2))


def test_make_key_differs_by_word_or_dictionary_set() -> None:
    base = query_cache.make_key("hello", (1,))
    assert base != query_cache.make_key("world", (1,))
    assert base != query_cache.make_key("hello", (1, 2))


def test_get_set_roundtrip_and_invalidate() -> None:
    key = query_cache.make_key("cacheword", (999,))
    assert query_cache.get(key) is None

    query_cache.set(key, [{"word": "cacheword"}])
    assert query_cache.get(key) == [{"word": "cacheword"}]

    query_cache.invalidate()
    assert query_cache.get(key) is None
