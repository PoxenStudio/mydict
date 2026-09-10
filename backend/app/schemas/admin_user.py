from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.vocab import VocabItemOut


class AdminUserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr | None = None


class AdminUserOut(BaseModel):
    id: int
    username: str
    email: str | None
    status: str
    created_at: datetime
    last_login_at: datetime | None
    vocab_count: int
    query_count: int


class AdminUserCreateResponse(BaseModel):
    user: AdminUserOut
    temporary_password: str


class AdminUserListResponse(BaseModel):
    items: list[AdminUserOut]
    total: int
    page: int
    page_size: int


class ResetPasswordResponse(BaseModel):
    temporary_password: str


class QueryLogOut(BaseModel):
    word: str
    status: str | None
    dictionary_id: int | None
    duration_ms: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserDetailResponse(BaseModel):
    user: AdminUserOut
    vocab_items: list[VocabItemOut]
    recent_queries: list[QueryLogOut]
