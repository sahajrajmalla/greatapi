"""The ``require_api_key`` dependency."""

from __future__ import annotations

import contextvars
import math
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from greatapi.db.base import utcnow
from greatapi.db.models import APIKey
from greatapi.keys.ratelimit import get_rate_limiter
from greatapi.keys.service import KeyRejection, monthly_spend, verify_api_key
from greatapi.security.dependencies import DbSession

__all__ = ["current_api_key", "require_api_key"]

_bearer = HTTPBearer(auto_error=False, description="API key as a bearer token")
_header = APIKeyHeader(name="X-API-Key", auto_error=False)

#: The key that authorised the current request, so usage recording can attribute
#: spend without every endpoint having to thread the object through by hand.
current_api_key: contextvars.ContextVar[APIKey | None] = contextvars.ContextVar(
    "greatapi_current_api_key", default=None
)


def require_api_key(
    *scopes: str,
) -> Callable[..., Coroutine[Any, Any, APIKey]]:
    """Require a valid API key, optionally carrying every scope in ``scopes``.

    ::

        @app.post("/chat")
        async def chat(key: APIKey = Depends(require_api_key("chat:write"))):
            ...

    Failure modes are distinguished so a client can act on them:
    ``401`` missing or invalid credentials, ``403`` authenticated but missing a
    scope, ``429`` over the per-minute rate limit (with ``Retry-After``), and
    ``402`` over the monthly spend cap.
    """

    async def dependency(
        request: Request,
        session: DbSession,
        bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
        header_key: Annotated[str | None, Depends(_header)] = None,
    ) -> APIKey:
        raw_key = header_key or (bearer.credentials if bearer else None)
        if not raw_key:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Missing API key. Send it as 'Authorization: Bearer <key>' or 'X-API-Key: <key>'.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        outcome = await verify_api_key(session, raw_key)
        if isinstance(outcome, KeyRejection):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                outcome.detail,
                headers={"WWW-Authenticate": "Bearer"},
            )

        key = outcome
        missing = [scope for scope in scopes if scope not in key.scopes]
        if missing:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"API key is missing required scope(s): {', '.join(missing)}.",
            )

        if key.rate_limit_per_minute:
            retry_after = await get_rate_limiter().hit(
                f"key:{key.id}", key.rate_limit_per_minute, 60.0
            )
            if retry_after is not None:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    f"Rate limit of {key.rate_limit_per_minute} requests/minute exceeded.",
                    headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
                )

        if key.monthly_budget_usd is not None:
            spent = await monthly_spend(session, key.id)
            if spent >= key.monthly_budget_usd:
                raise HTTPException(
                    status.HTTP_402_PAYMENT_REQUIRED,
                    f"Monthly budget of ${key.monthly_budget_usd:.2f} exhausted "
                    f"(${spent:.2f} used).",
                )

        key.last_used_at = utcnow()
        await session.commit()

        current_api_key.set(key)
        request.state.api_key = key
        return key

    return dependency
