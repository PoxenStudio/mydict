from datetime import datetime

from pydantic import BaseModel


class WebQueryResultItem(BaseModel):
    """前台查询结果：不带释义。前台的释义走 /dict/entry 渲染进隔离 iframe，这里再带一份
    完整 HTML 只是白白传输（搜韵「毛泽东」一次就是 82 首诗）、白占查询缓存。"""

    # 条目主键。同一部词典里可能有多条同名词条（MDict 允许），前端拿它做 key 与寻址
    id: int
    dictionary_id: int
    dictionary_name: str
    word: str
    phonetic: str | None
    extra: dict | None
    # 该词典的语言方向是否与输入一致。false 表示这是「优先语言都没命中、于是退到其余
    # 语言词典」的结果——语言方向是导入时自动识别的，可能判错，界面上要标出来。
    lang_match: bool = True


class WebQueryResponse(BaseModel):
    results: list[WebQueryResultItem]


class QueryResultItem(WebQueryResultItem):
    """对外 API（/api/v1/query）的查询结果：第三方拿不到 iframe，释义必须随结果返回。"""

    definition: str


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
