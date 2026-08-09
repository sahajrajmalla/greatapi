"""Issuing and verifying API keys.

Keys look like ``gapi_<prefix>_<secret>``. Only the SHA-256 digest is persisted,
so a database dump does not hand over working credentials. The prefix is stored
in clear purely so a human can tell two keys apart in the admin without the
system being able to reveal either.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from greatapi.db.base import utcnow
from greatapi.db.models import APIKey, LLMCall, User

__all__ = [
    "KEY_PREFIX",
    "create_api_key",
    "hash_key",
    "monthly_spend",
    "revoke_api_key",
    "verify_api_key",
]

KEY_PREFIX = "gapi"
_PREFIX_LENGTH = 8
_SECRET_LENGTH = 32
_SPEND_CACHE_TTL_SECONDS = 60.0


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def create_api_key(
    session: AsyncSession,
    *,
    name: str,
    scopes: list[str] | None = None,
    user: User | None = None,
    rate_limit_per_minute: int | None = None,
    monthly_budget_usd: float | None = None,
    expires_at: object | None = None,
) -> tuple[APIKey, str]:
    """Create a key and return ``(record, plaintext)``.

    The plaintext is the only copy that will ever exist -- show it once and
    forget it.
    """
    prefix = secrets.token_hex(_PREFIX_LENGTH // 2)
    secret = secrets.token_urlsafe(_SECRET_LENGTH)
    raw_key = f"{KEY_PREFIX}_{prefix}_{secret}"

    record = APIKey(
        name=name,
        prefix=prefix,
        hashed_key=hash_key(raw_key),
        scopes=scopes or [],
        rate_limit_per_minute=rate_limit_per_minute,
        monthly_budget_usd=monthly_budget_usd,
        expires_at=expires_at,
        user_id=user.id if user else None,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record, raw_key


@dataclass(frozen=True, slots=True)
class KeyRejection:
    """Why a key was refused, mapped to an HTTP status by the dependency."""

    reason: str
    detail: str
    retry_after: float | None = None


async def verify_api_key(session: AsyncSession, raw_key: str) -> APIKey | KeyRejection:
    """Resolve a plaintext key to its record, or explain why it was refused."""
    invalid = KeyRejection("invalid", "Invalid API key.")

    # maxsplit=2, because token_urlsafe emits '-' and '_' -- a plain split
    # would shred any secret containing an underscore, which is most of them.
    parts = raw_key.split("_", 2)
    if len(parts) != 3 or parts[0] != KEY_PREFIX or not parts[1] or not parts[2]:
        return invalid

    result = await session.execute(select(APIKey).where(APIKey.prefix == parts[1]))
    record = result.scalar_one_or_none()
    if record is None:
        return invalid

    if not secrets.compare_digest(record.hashed_key, hash_key(raw_key)):
        return invalid
    if not record.is_active:
        return KeyRejection("inactive", "This API key has been revoked.")
    if record.expires_at is not None and record.expires_at < utcnow():
        return KeyRejection("expired", "This API key has expired.")

    return record


async def revoke_api_key(session: AsyncSession, key_id: int) -> bool:
    record = await session.get(APIKey, key_id)
    if record is None:
        return False
    record.is_active = False
    await session.commit()
    return True


_spend_cache: dict[int, tuple[float, float]] = {}


async def monthly_spend(session: AsyncSession, key_id: int, *, use_cache: bool = True) -> float:
    """Total USD spent by a key since the start of the current UTC month.

    Cached briefly: a budget is a guard rail, not an accounting ledger, and
    aggregating on every single request would cost more than it saves.
    """
    now = time.monotonic()
    if use_cache:
        cached = _spend_cache.get(key_id)
        if cached is not None and now - cached[0] < _SPEND_CACHE_TTL_SECONDS:
            return cached[1]

    start_of_month = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await session.execute(
        select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).where(
            LLMCall.api_key_id == key_id, LLMCall.created_at >= start_of_month
        )
    )
    total = float(result.scalar_one())
    _spend_cache[key_id] = (now, total)
    return total


def clear_spend_cache() -> None:
    _spend_cache.clear()
