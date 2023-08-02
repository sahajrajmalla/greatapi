from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class CategoryEnum(str, Enum):
    edit = 'edit'
    create = 'create'
    delete = 'delete'


class HistoryCreateSchema(BaseModel):
    name: str
    category: CategoryEnum

    class Config:
        orm_mode = True


class HistorySchema(BaseModel):
    id: Optional[int]
    name: str
    category: str
    created_date: Optional[datetime]

    class Config:
        orm_mode = True
