from __future__ import annotations

from typing import List
from typing import Tuple

from fastapi import Depends
from sqlalchemy.orm import Session

from greatapi.core.users.query import create_new_user
from greatapi.core.users.query import get_user_by_id
from greatapi.db.database import get_db
from greatapi.schemas.user import UserType
from greatapi.utils.cbv import cbv
from greatapi.utils.inferring_router import InferringRouter

user_router = InferringRouter(tags=['Users'])


@cbv(user_router)
class UserSite:
    db: Session = Depends(get_db)

    @user_router.post('/user', response_model=List[Tuple[int, str]])
    def create_user(self, request: UserType) -> list[tuple[int, str]]:
        return create_new_user(request, self.db)

    @user_router.get('/user/{id}', response_model=List[Tuple[int, str]])
    def get_user(self, id: int) -> list[tuple[int, str]]:
        return get_user_by_id(id, self.db)
