from datetime import datetime
from typing import Any

from pydantic import BaseModel


class BackgroundTaskOut(BaseModel):
    id: int
    task_type: str
    title: str
    status: str
    progress_data: dict[str, Any]
    created_at: datetime
    updated_at: datetime
