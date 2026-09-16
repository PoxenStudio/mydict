from datetime import datetime
from typing import Any

from pydantic import BaseModel


class BackgroundTaskOut(BaseModel):
    id: int
    task_type: str
    title: str
    status: str
    progress_data: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
