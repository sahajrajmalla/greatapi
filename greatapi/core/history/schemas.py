from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class HistorySchema(BaseModel):
    id: Optional[int]
    name: str
    category: str
    created_date: Optional[datetime]

    class Config:
        orm_mode = True
