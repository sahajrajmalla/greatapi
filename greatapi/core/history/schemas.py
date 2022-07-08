from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ShowHistorySchema(BaseModel):
    id: int
    name: str
    type: str
    created_date: datetime
    edited_date: datetime

    class Config:
        orm_mode = True


class HistorySchema(BaseModel):
    name: str
    type: str

    class Config:
        orm_mode = True
