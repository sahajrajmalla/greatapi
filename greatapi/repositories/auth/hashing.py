from __future__ import annotations

from passlib.context import CryptContext

pwd_cxt = CryptContext(schemes=['bcrypt'], deprecated='auto')


class Hash:
    @staticmethod
    def bcrypt(password: str) -> CryptContext:
        return pwd_cxt.hash(password)

    @staticmethod
    def verify(hashed_password: str, plain_password: str) -> CryptContext:
        return pwd_cxt.verify(plain_password, hashed_password)
