from __future__ import annotations
from greatapi.utils.inferring_router import InferringRouter

from greatapi.utils.cbv import cbv


from fastapi import Depends

from greatapi.db.models.user import User

from greatapi.core.users.query import get_user_by_id
from greatapi.schemas.user import ShowUser
from greatapi.core.auth.jwt_token import get_current_user
from sqlalchemy.orm import Session

from greatapi.db.database import get_db

test_auth_router = InferringRouter(tags=['Test Authentication'])

@cbv(test_auth_router)
class TestAuthSite:
    current_user: User = Depends(get_current_user)
    db: Session = Depends(get_db)

    @test_auth_router.get('/test_auth_user/{id}', response_model=ShowUser)
    def get_user(self, id: int) -> ShowUser:
        return get_user_by_id(id, self.db)