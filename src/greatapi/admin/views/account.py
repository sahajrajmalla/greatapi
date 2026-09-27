"""The signed-in user's own account page."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import RedirectResponse
from starlette.responses import Response

from greatapi.admin.templating import flash_url, render
from greatapi.conf.settings import get_settings
from greatapi.db.models import AuditAction, AuditLog
from greatapi.security.dependencies import AdminUser, DbSession
from greatapi.security.passwords import (
    PasswordPolicyError,
    hash_password,
    validate_password,
    verify_password,
)
from greatapi.security.sessions import issue_session

__all__ = ["account_router"]

account_router = APIRouter(include_in_schema=False)


@account_router.get("/account")
async def account(request: Request, user: AdminUser) -> Response:
    return render(request, "account.html", {}, user=user, active="account")


@account_router.post("/account/password")
async def change_password(
    request: Request,
    session: DbSession,
    user: AdminUser,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
) -> Response:
    settings = get_settings()

    def fail(message: str) -> Response:
        return render(
            request,
            "account.html",
            {"error": message},
            user=user,
            active="account",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    valid, _ = verify_password(current_password, user.hashed_password)
    if not valid:
        return fail("Your current password is incorrect.")
    if new_password != confirm_password:
        return fail("The new passwords do not match.")
    try:
        validate_password(new_password)
    except PasswordPolicyError as exc:
        return fail(str(exc))

    user.hashed_password = hash_password(new_password)
    session.add(
        AuditLog(
            action=AuditAction.update,
            message=f"{user.username} changed their password",
            object_type="User",
            object_id=str(user.id),
            actor_id=user.id,
        )
    )
    await session.commit()

    # Rotate the session so the old cookie -- and its CSRF nonce -- stop working.
    response = RedirectResponse(
        flash_url(f"{settings.admin_path}/account", "password-changed"),
        status_code=status.HTTP_303_SEE_OTHER,
    )
    issue_session(response, user.id)
    return response
