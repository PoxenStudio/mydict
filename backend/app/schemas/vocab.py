from datetime import datetime

from pydantic import BaseModel, Field


class VocabCreateRequest(BaseModel):
    word: str = Field(min_length=1, max_length=255)
    dictionary_id: int | None = None
    note: str | None = None


class VocabItemOut(BaseModel):
    id: int
    word: str
    phonetic: str | None
    definition: str | None
    note: str | None
    dictionary_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class VocabListResponse(BaseModel):
    items: list[VocabItemOut]
    total: int
    page: int
    page_size: int
