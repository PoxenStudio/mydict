from pydantic import BaseModel


class OverviewOut(BaseModel):
    today_query_count: int
    active_tokens: int
    active_users: int
    dictionary_count: int


class StatRow(BaseModel):
    id: int | None
    label: str
    query_count: int
    rate_limited_count: int


class TopWordRow(BaseModel):
    word: str
    count: int
