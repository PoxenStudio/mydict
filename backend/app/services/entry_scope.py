from app.models.dictionary import DictEntry, Dictionary


def current_generation_only(query):
    """只保留各词典当前生效那一代的词条。

    重新解析期间，新一代词条已经写进 dict_entries，但在切换之前不能被查到；切换之后、
    旧一代删完之前，旧行同样不能被查到。所有读 dict_entries 的查询都必须经过这里。
    """
    return query.join(Dictionary, Dictionary.id == DictEntry.dictionary_id).filter(
        DictEntry.generation == Dictionary.active_generation
    )
