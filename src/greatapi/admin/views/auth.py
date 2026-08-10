"""Login and logout.

Authentication happens on the server. The 1.x admin checked ``is_admin`` from a
``window.onload`` handler, which meant every page's data had already been sent
before the check ran -- ``curl`` skipped it entirely.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import RedirectResponse
from starlette.responses import Response

from greatapi.admin.templating import render
from greatapi.conf.settings import get_settings
from greatapi.db.base import utcnow
from greatapi.db.models import AuditAction, AuditLog
from greatapi.keys.ratelimit import get_rate_limiter
from greatapi.security.dependencies import DbSession, authenticate_user
from greatapi.security.sessions import clear_session, issue_session

__all__ = ["auth_router"]

auth_router = APIRouter(include_in_schema=False)

#: Deliberately identical for "no such user", "wrong password" and "not an
#: admin". Distinct messages let an attacker enumerate accounts.
_LOGIN_FAILED = "Incorrect username or password."


#: A same-site destination: one leading slash, then nothing that could turn it
#: into an absolute or protocol-relative URL. Anything else falls back to the
#: admin root rather than being cleaned up -- a redirect target is not worth
#: guessing at.
_SAFE_NEXT = re.compile(r"^/(?![/\\])[^\\\s]*$")


def _safe_next(raw: str | None) -> str:
    r"""Return ``raw`` only if it is a same-site path, else the admin root.

    Rejects ``//evil.com`` and ``/\evil.com`` alike: browsers normalise a
    backslash to a forward slash, so the second is protocol-relative too and a
    naive ``startswith("//")`` check misses it. Whitespace and control
    characters are rejected for the same reason -- a browser may strip them and
    change what the URL means.
    """
    settings = get_settings()
    if raw and len(raw) <= 512 and _SAFE_NEXT.match(raw) and "\x00" not in raw:
        return raw
    return settings.admin_path


@auth_router.get("/login")
async def login_page(request: Request) -> Response:
    return render(request, "login.html", {"next": _safe_next(request.query_params.get("next"))})


@auth_router.post("/login")
async def login_submit(
    request: Request,
    session: DbSession,
    username: str = Form(...),
    password: str = Form(...),
    next_url: str = Form(default="", alias="next"),
) -> Response:
    target = _safe_next(next_url or None)
    client = request.client.host if request.client else "unknown"
    settings = get_settings()

    retry_after = await get_rate_limiter().hit(
        f"login:{client}", settings.login_rate_limit_per_minute, 60.0
    )
    if retry_after is not None:
        return render(
            request,
            "login.html",
            {"error": "Too many attempts. Try again shortly.", "next": target},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    user = await authenticate_user(session, username, password)
    if user is None or not user.is_admin:
        return render(
            request,
            "login.html",
            {"error": _LOGIN_FAILED, "next": target},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    response = RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    issue_session(response, user.id)

    session.add(
        AuditLog(
            action=AuditAction.login,
            message=f"{user.username} signed in",
            object_type="User",
            object_id=str(user.id),
            actor_id=user.id,
        )
    )
    user.last_login_at = utcnow()
    await session.commit()
    return response


@auth_router.post("/logout")
async def logout(request: Request) -> Response:
    settings = get_settings()
    response = RedirectResponse(
        f"{settings.admin_path}/login?flash=logged-out", status_code=status.HTTP_303_SEE_OTHER
    )
    clear_session(response)
    return response
