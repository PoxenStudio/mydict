from datetime import datetime

from pydantic import BaseModel, Field


class VocabCreateRequest(BaseModel):
    word: str = Field(min_length=1, max_length=255)
    dictionary_id: int | None = None
    note: str | None = None
    # 句子挖矿（可选）：收藏时把遇到它的那句话一起存下来
    context_sentence: str | None = Field(default=None, max_length=1000)
    context_match: str | None = Field(default=None, max_length=64)
    context_source: str | None = Field(default=None, max_length=255)
    context_url: str | None = Field(default=None, max_length=1000)


class VocabItemOut(BaseModel):
    id: int
    word: str
    phonetic: str | None
    definition: str | None
    note: str | None
    dictionary_id: int | None
    # 来源词典名快照（词典被删后仍显示）
    dictionary_name: str | None = None
    created_at: datetime
    # 复习调度（FSRS）：due_at 为 UTC；reps 为 0 表示还没复习过的新词
    due_at: datetime | None = None
    reps: int = 0
    lapses: int = 0
    last_review_at: datetime | None = None
    # 句子挖矿：原句 + 句中实际词形 + 来源（网页标题/书名）
    context_sentence: str | None = None
    context_match: str | None = None
    context_source: str | None = None
    context_url: str | None = None

    model_config = {"from_attributes": True}


class VocabListResponse(BaseModel):
    items: list[VocabItemOut]
    total: int
    page: int
    page_size: int


class VocabCounts(BaseModel):
    """生词本口径：total 全部，new 未复习过，due 已到期待复习。"""

    total: int
    new: int
    due: int


class VocabDueResponse(BaseModel):
    items: list[VocabItemOut]
    counts: VocabCounts


class VocabReviewRequest(BaseModel):
    # 1=Again 2=Hard 3=Good 4=Easy
    rating: int = Field(ge=1, le=4)
    # 离线补交时传当时的复习时间（UTC）；不传则用服务器当前时间
    reviewed_at: datetime | None = None
    client: str | None = Field(default=None, max_length=16)
    client_review_id: str | None = Field(default=None, max_length=64)


class VocabReviewResponse(BaseModel):
    item: VocabItemOut
    counts: VocabCounts


class VocabStatsResponse(BaseModel):
    total: int
    new: int
    due: int
    learned: int
    reviewed_today: int
    scheduled_total: int
