"""Authentication dependencies and helpers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from greatapi.conf.settings import get_settings
from greatapi.db.base import utcnow
from greatapi.db.models import User
from greatapi.db.session import get_session
from greatapi.security.passwords import verify_password
from greatapi.security.sessions import read_session

__all__ = [
    "AdminUser",
    "CurrentUser",
    "DbSession",
    "NotAuthenticated",
    "authenticate_user",
    "get_current_user",
    "require_admin",
    "require_user",
]

DbSession = Annotated[AsyncSession, Depends(get_session)]


class NotAuthenticated(HTTPException):
    """Raised when an admin page is requested without a valid session.

    The application converts this into a redirect to the login page for browser
    navigations, and leaves it as a 401 for API clients.
    """

    def __init__(self) -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, "Not authenticated.")


async def authenticate_user(session: AsyncSession, identifier: str, password: str) -> User | None:
    """Verify credentials by email or username.

    Returns ``None`` for an unknown user, a wrong password, or a deactivated
    account -- deliberately indistinguishable, so callers cannot turn this into
    an account-enumeration oracle. The password is verified against a dummy hash
    when the user does not exist, keeping the timing of both paths comparable.
    """
    result = await session.execute(
        select(User).where((User.email == identifier) | (User.username == identifier))
    )
    user = result.scalar_one_or_none()

    valid, upgraded = verify_password(password, user.hashed_password if user else None)
    if user is None or not valid or not user.is_active:
        return None

    if upgraded is not None:
        user.hashed_password = upgraded
    user.last_login_at = utcnow()
    await session.commit()
    return user


async def get_current_user(request: Request, session: DbSession) -> User | None:
    """Return the signed-in user, or ``None``. Never raises."""
    signed = read_session(request)
    if signed is None:
        return None
    user = await session.get(User, signed.user_id)
    if user is None or not user.is_active:
        return None
    return user


async def require_user(
    user: Annotated[User | None, Depends(get_current_user)],
) -> User:
    """Require any authenticated, active user."""
    if user is None:
        raise NotAuthenticated()
    return user


async def require_admin(
    user: Annotated[User | None, Depends(get_current_user)],
) -> User:
    """Require an authenticated administrator.

    Applied as a router-level dependency across the whole admin, so a new view
    is protected by default instead of by remembering to protect it.
    """
    if user is None:
        raise NotAuthenticated()
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required.")
    return user


CurrentUser = Annotated[User | None, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]


def login_redirect(request: Request) -> RedirectResponse:
    """Send a browser to the login page, remembering where it was going."""
    settings = get_settings()
    target = request.url.path
    query = f"?next={target}" if target and target != f"{settings.admin_path}/login" else ""
    return RedirectResponse(
        f"{settings.admin_path}/login{query}", status_code=status.HTTP_303_SEE_OTHER
    )
