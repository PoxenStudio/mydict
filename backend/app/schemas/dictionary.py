from datetime import datetime

from pydantic import BaseModel, Field

VALID_FORMATS = ("mdict", "stardict", "ecdict")


class DictionaryOut(BaseModel):
    id: int
    name: str
    format: str
    lang_from: str
    lang_to: str
    word_count: int
    sort_order: int
    status: str
    import_method: str
    imported_at: datetime

    model_config = {"from_attributes": True}


class DictsDirFileOut(BaseModel):
    name: str
    size: int
    modified_at: datetime
    imported: bool
    is_dir: bool = False


class DictsDirListingOut(BaseModel):
    """当前目录下的条目列表；path 为相对 /data/dicts 的归一化路径，根目录是空串。"""

    path: str
    entries: list[DictsDirFileOut]


class ImportFromDictsDirRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    format: str
    lang_from: str = Field(min_length=1, max_length=8)
    lang_to: str = Field(min_length=1, max_length=8)
    files: list[str] = Field(min_length=1)


class ReorderRequest(BaseModel):
    ordered_ids: list[int] = Field(min_length=1)


class AllowedDictionaryIdsRequest(BaseModel):
    """Token/用户「可用词典」设置共用的请求体：dictionary_ids 为 None 表示不限制。"""

    dictionary_ids: list[int] | None = None


class TestQueryEntryOut(BaseModel):
    word: str
    phonetic: str | None
    definition: str
    extra: dict | None

    model_config = {"from_attributes": True}
