from __future__ import annotations

from pydantic import BaseModel


class LoginSchema(BaseModel):
    username: str
    password: str


class TokenData(BaseModel):
    username: str
