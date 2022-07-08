from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class UserSchema(BaseModel):
    id: Optional[int]
    name: str
    email: str
    password: str
    username: str
    contact_number: str

    class Config():
        orm_mode = True


class ShowUserSchema(BaseModel):
    id: Optional[int]
    name: str
    email: str
    username: str
    contact_number: str

    class Config():
        orm_mode = True
