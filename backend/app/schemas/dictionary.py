from datetime import datetime
from typing import Literal

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


class DictsDirGroupFileOut(BaseModel):
    name: str
    relpath: str
    size: int
    imported: bool


class DictsDirGroupOut(BaseModel):
    """扫描时按 (格式, 主干) 归组出来的一个待导入词典单元。"""

    key: str
    name: str
    format: str
    dir: str
    files: list[DictsDirGroupFileOut]
    total_size: int
    importable: bool
    reason: str | None = None
    imported: bool = False


class DictsDirListingOut(BaseModel):
    """当前目录下的条目列表；path 为相对 /data/dicts 的归一化路径，根目录是空串。

    entries 是原始目录列表（前端据此下钻子目录），dictionaries 是把同目录文件按
    (格式, 主干) 归组后的待导入单元，skipped 是被忽略的无关文件名。
    """

    path: str
    entries: list[DictsDirFileOut]
    dictionaries: list[DictsDirGroupOut]
    skipped: list[str]


class DictionaryImportTaskOut(BaseModel):
    """导入接口不再同步等解析入库跑完才返回，立即给出 task_id，前端轮询
    GET /admin/tasks/{task_id} 直到 status 变成 success/error 才算真正完成。"""

    task_id: int


class ImportFromDictsDirRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    format: str
    # 留空表示导入时自动识别
    lang_from: str | None = Field(default=None, max_length=8)
    lang_to: str | None = Field(default=None, max_length=8)
    # 只导入释义，不解包 .mdd 里的图片/发音
    skip_resources: bool = False
    files: list[str] = Field(min_length=1)


class DictionaryUpdateRequest(BaseModel):
    """只允许改名称与语言方向；format 决定了当初怎么解析入库，改了也不会重新解析，不开放修改。"""

    name: str = Field(min_length=1, max_length=255)
    lang_from: str = Field(min_length=1, max_length=8)
    lang_to: str = Field(min_length=1, max_length=8)


class ReorderRequest(BaseModel):
    ordered_ids: list[int] = Field(min_length=1)


class BatchStatusRequest(BaseModel):
    dictionary_ids: list[int] = Field(min_length=1, max_length=500)
    status: Literal["enabled", "disabled"]


class RenameDictionariesRequest(BaseModel):
    """按正则批量重命名词典。

    pattern 用 Python re 语法，replacement 支持 `\\1` 这类反向引用。dictionary_ids 留空表示
    对全部词典生效。dry_run 默认 True：先预览一遍再应用，正则写错一次就能改坏几十个名字。
    """

    pattern: str = Field(min_length=1, max_length=200)
    replacement: str = Field(default="", max_length=255)
    dictionary_ids: list[int] | None = None
    dry_run: bool = True


class RenamePreviewItemOut(BaseModel):
    id: int
    name: str
    new_name: str


class RenameDictionariesOut(BaseModel):
    """只回会被改名的那些：一次正则可能扫过几百部词典，把没命中的也回给前端没有意义。"""

    items: list[RenamePreviewItemOut]
    applied: bool


class SpxScanRequest(BaseModel):
    """dictionary_ids 留空表示扫描全部词典。"""

    dictionary_ids: list[int] | None = None


class SpxTranscodeRequest(BaseModel):
    """单部与批量共用：列表长度 1 就是单部。"""

    dictionary_ids: list[int] = Field(min_length=1, max_length=500)


class AllowedDictionaryIdsRequest(BaseModel):
    """Token/用户「可用词典」设置共用的请求体：dictionary_ids 为 None 表示不限制。"""

    dictionary_ids: list[int] | None = None


class TestQueryEntryOut(BaseModel):
    word: str
    phonetic: str | None
    definition: str
    extra: dict | None

    model_config = {"from_attributes": True}
