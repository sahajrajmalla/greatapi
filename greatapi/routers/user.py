from fastapi import APIRouter, Depends
from greatapi.db.database import get_db
from greatapi.repositories.users.user import *
from greatapi.schemas.user import ShowUser, UserType
from sqlalchemy.orm import Session

router = APIRouter(prefix="/user", tags=["Users"])


@router.post("/", response_model=ShowUser)
def create_user(request: UserType, db: Session = Depends(get_db)):
    return create_new_user(request, db)


@router.get("/{id}", response_model=ShowUser)
def get_user(id: int, db: Session = Depends(get_db)):
    return get_user_by_id(id, db)
