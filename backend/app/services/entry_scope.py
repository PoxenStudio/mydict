from sqlalchemy import and_

from app.models.dictionary import DictEntry, Dictionary

# BINARY 排序下，以 p 开头的串都落在 [p, p + U+10FFFF) 区间里
_PREFIX_UPPER_BOUND = "\U0010ffff"


def current_generation_only(query):
    """只保留各词典当前生效那一代的词条。

    重新解析期间，新一代词条已经写进 dict_entries，但在切换之前不能被查到；切换之后、
    旧一代删完之前，旧行同样不能被查到。所有读 dict_entries 的查询都必须经过这里。
    """
    return query.join(Dictionary, Dictionary.id == DictEntry.dictionary_id).filter(
        DictEntry.generation == Dictionary.active_generation
    )


def in_dictionary_for_id_window(dictionary_id: int):
    """按主键区间分批处理某部词典时用的词典过滤条件。

    写成 `dictionary_id + 0 = ?` 是故意的：表达式用不上索引，SQLite 只能走主键区间。
    库里没有 ANALYZE 统计时，规划器会优先用 (dictionary_id, word_lower) 索引的等值匹配而
    放弃主键区间，于是每一批都把整部词典的索引项扫一遍——搜韵 800 多万条、几百上千批，
    分批就失去了意义。
    """
    return (DictEntry.dictionary_id + 0) == dictionary_id


def word_lower_prefix(prefix_lower: str):
    """词头前缀匹配：`word_lower` 以 `prefix_lower`（调用方已小写）开头。

    写成区间比较而不是 `LIKE 'p%'`：默认的 LIKE 大小写不敏感，与 BINARY 索引排序对不上，
    规划器只能按 dictionary_id 收窄后逐行求值（搜韵 826 万行要几秒）；区间比较直接走
    (dictionary_id, word_lower) 索引区间读。也没有通配符，用户输入的 `%`、`_` 按字面匹配。
    """
    return and_(
        DictEntry.word_lower >= prefix_lower,
        DictEntry.word_lower < prefix_lower + _PREFIX_UPPER_BOUND,
    )
