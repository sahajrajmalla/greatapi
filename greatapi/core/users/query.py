from __future__ import annotations

from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from greatapi.core.auth.hashing import Hash
from greatapi.core.users.schemas import ShowUserSchema
from greatapi.core.users.schemas import UserSchema
from greatapi.db.admin.user import User


def create_new_user(request: UserSchema, db: Session) -> UserSchema:
    new_user = User(
        name=request.name,
        email=request.email,
        password=Hash.bcrypt(request.password),
        username=request.username,
        contact_number=request.contact_number,

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
