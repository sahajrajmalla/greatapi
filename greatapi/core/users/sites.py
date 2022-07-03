from __future__ import annotations
from greatapi.utils.inferring_router import InferringRouter

from greatapi.utils.cbv import cbv


from fastapi import Depends

from sqlalchemy.orm import Session

from greatapi.db.database import get_db

from greatapi.core.users.query import create_new_user
from greatapi.core.users.query import get_user_by_id
from greatapi.schemas.user import ShowUser
from greatapi.schemas.user import UserType

user_router = InferringRouter(tags=['Users'])

@cbv(user_router)
class UserSite:
    db: Session = Depends(get_db)

    @user_router.post('/user', response_model=ShowUser)
    def create_user(self, request: UserType) -> ShowUser:
        return create_new_user(request, self.db)


    @user_router.get('/user/{id}', response_model=ShowUser)
    def get_user(self, id: int) -> ShowUser:
        return get_user_by_id(id, self.db)