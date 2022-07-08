from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HistorySchema(BaseModel):
    id: int | None
    name: str
    type: str
    created_date: datetime | None
    edited_date: datetime | None

    class Config:
        orm_mode = True
