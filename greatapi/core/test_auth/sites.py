from __future__ import annotations

from typing import List
from typing import Tuple

from fastapi import Depends

from greatapi.core.auth.jwt_token import get_current_user
from greatapi.core.users.query import get_user_by_id
from greatapi.db.admin.user import User
from greatapi.db.database import SessionLocal
from greatapi.utils.cbv import cbv
from greatapi.utils.inferring_router import InferringRouter

test_auth_router = InferringRouter(tags=['Test Authentication'])


@cbv(test_auth_router)
class TestAuthSite:

    db = SessionLocal()

    @test_auth_router.get('/test_auth_user/{id}', response_model=List[Tuple[int, str]])
    def get_user(self, id: int, current_user: User = Depends(get_current_user)) -> list[tuple[int, str]]:
        return get_user_by_id(id, self.db)
