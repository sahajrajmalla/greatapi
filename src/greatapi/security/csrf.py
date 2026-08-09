"""CSRF protection for admin form posts."""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

from greatapi.security.sessions import read_session

__all__ = ["CSRF_FIELD_NAME", "CSRF_HEADER_NAME", "verify_csrf"]

CSRF_FIELD_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"


async def verify_csrf(request: Request) -> None:
    """Reject unsafe requests whose CSRF token does not match the session.

    Used as a router dependency on every state-changing admin route. Safe
    methods pass through untouched.
    """
    if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return

    session = read_session(request)
    if session is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing session.")

    submitted = request.headers.get(CSRF_HEADER_NAME)
    if submitted is None:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith(("application/x-www-form-urlencoded", "multipart/form-data")):
            form = await request.form()
            value = form.get(CSRF_FIELD_NAME)
            submitted = value if isinstance(value, str) else None

    if not submitted or not secrets.compare_digest(submitted, session.csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid.")
