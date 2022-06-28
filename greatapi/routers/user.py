from __future__ import annotations

from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy.orm import Session

from greatapi.db.database import get_db
from greatapi.repositories.users.user import create_new_user
from greatapi.repositories.users.user import get_user_by_id
from greatapi.schemas.user import ShowUser
from greatapi.schemas.user import UserType

router = APIRouter(prefix='/user', tags=['Users'])


@router.post('/', response_model=ShowUser)
def create_user(request: UserType, db: Session = Depends(get_db)) -> ShowUser:
    return create_new_user(request, db)


@router.get('/{id}', response_model=ShowUser)
def get_user(id: int, db: Session = Depends(get_db)) -> ShowUser:
    return get_user_by_id(id, db)
