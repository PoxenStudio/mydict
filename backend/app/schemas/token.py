from datetime import datetime

from pydantic import BaseModel, Field


class TokenCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    daily_limit: int | None = None
    allowed_dictionary_ids: list[int] | None = None


class TokenOut(BaseModel):
    id: int
    name: str
    token_prefix: str
    daily_limit: int | None
    status: str
    created_at: datetime
    last_used_at: datetime | None
    today_count: int
    total_count: int
    allowed_dictionary_ids: list[int] | None


class TokenCreateResponse(TokenOut):
    token: str
