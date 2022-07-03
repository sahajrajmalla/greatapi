from __future__ import annotations
from greatapi.utils.inferring_router import InferringRouter

from greatapi.utils.cbv import cbv

from typing import Any
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from greatapi.db.database import get_db
from greatapi.db.models.user import User
from greatapi.core.auth.hashing import Hash
from greatapi.core.auth.jwt_token import create_access_token


auth_router = InferringRouter(tags=['Authentication'])

@cbv(auth_router)
class AuthSite:
    db: Session = Depends(get_db)


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