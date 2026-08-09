"""User creation for the CLI."""

from __future__ import annotations

from sqlalchemy import select

from greatapi.db.models import User
from greatapi.db.session import create_all, get_engine, session_scope
from greatapi.exceptions import GreatAPIError
from greatapi.security.passwords import PasswordPolicyError, hash_password, validate_password

__all__ = ["create_superuser"]


async def create_superuser(
    email: str, username: str, password: str, full_name: str | None = None
) -> User:
    """Create an administrator, creating the tables first if they are missing.

    1.x required running the server once before ``createsuperuser`` would work,
    because only the server created tables. It also let you create two users
    with the same email, and only one of them could ever log in.
    """
    try:
        validate_password(password)
    except PasswordPolicyError as exc:
        raise GreatAPIError(str(exc)) from exc

    await _ensure_schema()

    async with session_scope() as session:
        clash = (
            await session.execute(
                select(User).where((User.email == email) | (User.username == username))
            )
        ).scalar_one_or_none()
        if clash is not None:
            field = "email" if clash.email == email else "username"
            raise GreatAPIError(f"A user with that {field} already exists.")

        user = User(
            email=email,
            username=username,
            full_name=full_name,
            hashed_password=hash_password(password),
            is_admin=True,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user


async def _ensure_schema() -> None:
    from sqlalchemy import inspect

    engine = get_engine()
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    if User.__tablename__ not in tables:
        await create_all()
