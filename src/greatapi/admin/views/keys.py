"""API key management.

The plaintext key is displayed exactly once, immediately after creation. Only
its SHA-256 digest is stored, so there is no "reveal" action to build -- the
server genuinely cannot show it again.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from starlette.responses import Response

from greatapi.admin.templating import flash_url, render
from greatapi.conf.settings import get_settings
from greatapi.db.base import utcnow
from greatapi.db.models import APIKey
from greatapi.keys.service import create_api_key, monthly_spend, revoke_api_key
from greatapi.security.dependencies import AdminUser, DbSession

__all__ = ["keys_router"]

keys_router = APIRouter(include_in_schema=False)


@keys_router.get("/api-keys")
async def key_list(request: Request, session: DbSession, user: AdminUser) -> Response:
    records = list(
        (await session.execute(select(APIKey).order_by(APIKey.created_at.desc()))).scalars()
    )
    spend = {record.id: await monthly_spend(session, record.id) for record in records}

    return render(
        request,
        "api_keys.html",
        {
            "keys": records,
            "spend": spend,
            "now": utcnow(),
            # Handed over by the redirect after creation, shown once, never stored.
            "new_key": request.query_params.get("key"),
        },
        user=user,
        active="api-keys",
    )


@keys_router.post("/api-keys")
async def create_key(
    session: DbSession,
    user: AdminUser,
    name: str = Form(..., min_length=1, max_length=120),
    scopes: str = Form(""),
    rate_limit_per_minute: str = Form(""),
    monthly_budget_usd: str = Form(""),
    expires_at: str = Form(""),
) -> Response:
    settings = get_settings()

    _, raw_key = await create_api_key(
        session,
        name=name.strip(),
        scopes=[scope.strip() for scope in scopes.replace(",", " ").split() if scope.strip()],
        user=user,
        rate_limit_per_minute=_optional_int(rate_limit_per_minute, "rate limit"),
        monthly_budget_usd=_optional_float(monthly_budget_usd, "monthly budget"),
        expires_at=_optional_datetime(expires_at),
    )

    return RedirectResponse(
        flash_url(f"{settings.admin_path}/api-keys", "created", key=raw_key),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@keys_router.post("/api-keys/{key_id}/revoke")
async def revoke_key(session: DbSession, user: AdminUser, key_id: int) -> Response:
    settings = get_settings()
    if not await revoke_api_key(session, key_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such API key.")
    return RedirectResponse(
        flash_url(f"{settings.admin_path}/api-keys", "key-revoked"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _optional_int(raw: str, label: str) -> int | None:
    if not raw.strip():
        return None
    try:
        value = int(raw)
    except ValueError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Enter a whole number for {label}."
        ) from None
    if value < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"The {label} must be at least 1.")
    return value


def _optional_float(raw: str, label: str) -> float | None:
    if not raw.strip():
        return None
    try:
        value = float(raw)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Enter a number for {label}.") from None
    if value <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"The {label} must be greater than zero.")
    return value


def _optional_datetime(raw: str) -> datetime | None:
    if not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter a valid expiry date.") from None
