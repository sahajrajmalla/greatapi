from __future__ import annotations

from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from greatapi.core.auth.hashing import Hash
from greatapi.db.models.user import User
from greatapi.schemas.user import ShowUserSchema
from greatapi.schemas.user import UserSchema


def create_new_user(request: UserSchema, db: Session) -> UserSchema:
    new_user = User(
        name=request.name,
        email=request.email,
        password=Hash.bcrypt(request.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


def get_user_by_id(id: int, db: Session) -> ShowUserSchema:
    user = db.query(User).filter(User.id == id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'User id {id} does not exist.',
        )

    return user
