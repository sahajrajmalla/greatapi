# createsuperuser.py
from __future__ import annotations

from getpass import getpass

from sqlalchemy.orm import Session

from greatapi.core.auth.hashing import Hash
from greatapi.core.users.schemas import UserSchema
from greatapi.db.admin.user import User
from greatapi.db.database import SessionLocal

db = SessionLocal()


def create_superuser_interactive(db: Session = db) -> None:
    print('Create Superuser')
    name = input('Name: ')
    email = input('Email: ')
    username = input('Username: ')
    contact_number = input('Contact Number: ')
    password = getpass('Password: ')
    password_confirm = getpass('Confirm Password: ')

    if password != password_confirm:
        print('Passwords do not match. Please try again.')
        return

    request = UserSchema(
        name=name,
        email=email,
        username=username,
        contact_number=contact_number,
        password=password,
    )

    new_user = User(
        name=request.name,
        email=request.email,
        password=Hash.bcrypt(request.password),
        username=request.username,
        contact_number=request.contact_number,
        is_admin=True,  # Set the is_admin field to True for the superuser
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    print('Superuser created successfully.')
