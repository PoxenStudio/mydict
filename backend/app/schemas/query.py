from datetime import datetime

from pydantic import BaseModel


class QueryResultItem(BaseModel):
    dictionary_id: int
    dictionary_name: str
    word: str
    phonetic: str | None
    definition: str
    extra: dict | None


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
