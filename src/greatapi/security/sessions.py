"""Admin session cookies.

The admin authenticates with a signed, ``HttpOnly`` cookie rather than a token in
``localStorage``. A token readable by JavaScript is a token any XSS on the page
can exfiltrate; a ``HttpOnly`` cookie is not, and it is sent automatically so the
templates need no bearer-token plumbing.

The CSRF nonce is carried *inside* the signed session, so the double-submit check
compares a value the client cannot forge against one it cannot read.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

from starlette.requests import Request
from starlette.responses import Response

from greatapi.conf.settings import get_settings
from greatapi.security.tokens import TokenError, create_token, decode_token

__all__ = ["Session", "clear_session", "issue_session", "read_session"]

_SESSION_TYPE = "session"


@dataclass(frozen=True, slots=True)
class Session:
    user_id: int
    csrf_token: str


def issue_session(response: Response, user_id: int) -> Session:
    """Attach a fresh signed session cookie to ``response``."""
    settings = get_settings()
    csrf_token = secrets.token_urlsafe(32)
    token = create_token(
        str(user_id),
        token_type=_SESSION_TYPE,
        expires_in=timedelta(seconds=settings.session_max_age_seconds),
        csrf=csrf_token,
    )
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=bool(settings.session_cookie_secure),
        samesite="lax",
        path="/",
    )
    return Session(user_id=user_id, csrf_token=csrf_token)


def read_session(request: Request) -> Session | None:
    """Return the verified session on ``request``, or ``None``."""
    settings = get_settings()
    raw = request.cookies.get(settings.session_cookie_name)
    if not raw:
        return None
    try:
        claims = decode_token(raw, expected_type=_SESSION_TYPE)
    except TokenError:
        return None
    csrf_token = claims.get("csrf")
    if not isinstance(csrf_token, str):
        return None
    try:
        user_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError):
        return None
    return Session(user_id=user_id, csrf_token=csrf_token)


def clear_session(response: Response) -> None:
    """Remove the session cookie."""
    settings = get_settings()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=bool(settings.session_cookie_secure),
        samesite="lax",
    )
