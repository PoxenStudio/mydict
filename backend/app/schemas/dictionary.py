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
    imported_at: datetime

    model_config = {"from_attributes": True}


class DictsDirFileOut(BaseModel):
    name: str
    size: int
    modified_at: datetime


class ImportFromDictsDirRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    format: str
    lang_from: str = Field(min_length=1, max_length=8)
    lang_to: str = Field(min_length=1, max_length=8)
    files: list[str] = Field(min_length=1)


class ReorderRequest(BaseModel):
    ordered_ids: list[int] = Field(min_length=1)


class TestQueryEntryOut(BaseModel):
    word: str
    phonetic: str | None
    definition: str
    extra: dict | None

    model_config = {"from_attributes": True}
