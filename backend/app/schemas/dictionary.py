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


class DictionaryImportTaskOut(BaseModel):
    """导入接口不再同步等解析入库跑完才返回，立即给出 task_id，前端轮询
    GET /admin/tasks/{task_id} 直到 status 变成 success/error 才算真正完成。"""

    task_id: int


class ImportFromDictsDirRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    format: str
    lang_from: str = Field(min_length=1, max_length=8)
    lang_to: str = Field(min_length=1, max_length=8)
    files: list[str] = Field(min_length=1)


class DictionaryUpdateRequest(BaseModel):
    """只允许改名称与语言方向；format 决定了当初怎么解析入库，改了也不会重新解析，不开放修改。"""

    name: str = Field(min_length=1, max_length=255)
    lang_from: str = Field(min_length=1, max_length=8)
    lang_to: str = Field(min_length=1, max_length=8)


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
