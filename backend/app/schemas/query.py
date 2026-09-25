from datetime import datetime

from pydantic import BaseModel


class QueryResultItem(BaseModel):
    # 条目主键。同一部词典里可能有多条同名词条（MDict 允许），前端拿它做 key 与寻址
    id: int
    dictionary_id: int
    dictionary_name: str
    word: str
    phonetic: str | None
    definition: str
    extra: dict | None
    # 该词典的语言方向是否与输入一致。false 表示这是「优先语言都没命中、于是退到其余
    # 语言词典」的结果——语言方向是导入时自动识别的，可能判错，界面上要标出来。
    lang_match: bool = True


class QueryResponse(BaseModel):
    results: list[QueryResultItem]


class SuggestResponse(BaseModel):
    words: list[str]


class PublicDictionaryOut(BaseModel):
    id: int
    name: str
    lang_from: str
    lang_to: str

    model_config = {"from_attributes": True}


class QueryHistoryEntryOut(BaseModel):
    word: str
    dictionary_id: int
    dictionary_name: str
    created_at: datetime


class QueryHistoryResponse(BaseModel):
    items: list[QueryHistoryEntryOut]
