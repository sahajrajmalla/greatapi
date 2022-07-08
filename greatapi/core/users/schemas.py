from __future__ import annotations

from pydantic import BaseModel


class UserSchema(BaseModel):
    name: str
    email: str
    password: str

    class Config():
        orm_mode = True


class ShowUserSchema(BaseModel):
    name: str
    email: str

    class Config():
        orm_mode = True
