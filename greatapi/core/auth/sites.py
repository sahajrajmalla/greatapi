from __future__ import annotations

from typing import Any

from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from fastapi.security import OAuth2PasswordRequestForm

from greatapi.core.auth.hashing import Hash
from greatapi.core.auth.jwt_token import create_access_token
from greatapi.db.admin.user import User
from greatapi.db.database import SessionLocal
from greatapi.utils.cbv import cbv
from greatapi.utils.inferring_router import InferringRouter


auth_router = InferringRouter(tags=['Authentication'])


@cbv(auth_router)
class AuthSite:
    db = SessionLocal()

    @auth_router.post('/login')
    def login(self, request: OAuth2PasswordRequestForm = Depends()) -> dict[str, Any]:
        user = self.db.query(User).filter(User.email == request.username).first()
        plain_password = request.password
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Invalid Credentials',
            )

        if not Hash.verify(user.password, plain_password):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Incorrect Password',
            )

        # Generate a JWT token and return
        access_token = create_access_token(data={'sub': user.email})

        return {'access_token': access_token, 'token_type': 'bearer'}

    @auth_router.post('/admin_login')
    def admin_login(self, request: OAuth2PasswordRequestForm = Depends()) -> dict[str, Any]:
        user = self.db.query(User).filter(User.email == request.username).first()
        plain_password = request.password
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Invalid Credentials',
            )

        if not Hash.verify(user.password, plain_password):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Incorrect Password',
            )

        if not user.is_admin:  # Check if the user is an admin
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Access denied. Only admin users are allowed to login.',
            )
        # Generate a JWT token and return
        access_token = create_access_token(data={'sub': user.email})

        return {'access_token': access_token, 'token_type': 'bearer'}
