"""把一次查询扩展成一组等价写法（繁简、全角/半角），用于「繁简通搜」。

词典收录哪种写法并不统一：同一部词典可能只收繁体、另一部只收简体，还有的只收全角。
用户输入的是哪一种取决于习惯与输入法，如果查询时不做扩展，就只能命中写法恰好一致的
那一两部词典——实测用户的库里既有简体词典（千篇汉语词典2021）也有大量繁体词典
（大辭海、漢語大詞典、詩詞鑑賞大全），不做扩展就总有一半查不到。

这里只做「同一条词条的不同写法」这一层，**不做模糊匹配**：扩展出来的变体与原词是同一个
词的等价形式，不是相似词。
"""

import unicodedata
from functools import lru_cache

# 扩展规则一有变化就递增，让查询缓存整体失效——否则旧结果会在 TTL 内继续被命中。
# v2：search 加了「精确未命中 → 前缀兜底」，旧缓存里的空/少结果要整体作废。
EXPANSION_VERSION = 2

# 繁简转换是「一对多」的（发 → 發/髮），且不同地区用字不同，所以多取几个配置一起用，
# 尽量覆盖各词典实际采用的写法。
_OPENCC_CONFIGS = ("t2s", "s2t", "s2tw", "s2hk")

# 变体数上限：再多基本是重复，却会让 SQL 的 IN 列表与缓存 key 无谓变长。
_MAX_VARIANTS = 16

# ASCII 可见字符与全角形式之间的固定码点差
_FULLWIDTH_OFFSET = 0xFEE0
_ASCII_PRINTABLE = range(0x21, 0x7F)


def _to_fullwidth(text: str) -> str:
    """把 ASCII 可见字符转成全角（用户输入半角、词典里存的却是全角时的兜底）。"""
    return "".join(
        chr(ord(ch) + _FULLWIDTH_OFFSET) if ord(ch) in _ASCII_PRINTABLE else ch for ch in text
    )


def _normalize_width(text: str) -> str:
    """NFKC 归一：全角 ASCII 收成半角，半角片假名（ﾊﾝｶｸ）连浊点一起合成常规写法。"""
    return unicodedata.normalize("NFKC", text)


@lru_cache(maxsize=1)
def _converters() -> tuple:
    """OpenCC 实例较贵，进程内建一次即可。"""
    from opencc import OpenCC

    return tuple(OpenCC(name) for name in _OPENCC_CONFIGS)


def expand_word(word: str) -> list[str]:
    """返回该词的全部查询变体，含原词、已去重、已小写。第一个元素一定是原词。"""
    variants: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        if not value or len(variants) >= _MAX_VARIANTS:
            return
        key = value.strip().lower()
        if not key or key in seen:
            return
        seen.add(key)
        variants.append(key)

    # 先取形态变体（原样 / 宽度归一 / 全角），再对每种形态取繁简变体
    for base in (word, _normalize_width(word), _to_fullwidth(word)):
        add(base)
        for converter in _converters():
            try:
                add(converter.convert(base))
            except Exception:  # noqa: BLE001 - 转换失败只是少一个变体，不该影响查询
                continue
    return variants
