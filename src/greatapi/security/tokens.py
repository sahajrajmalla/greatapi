"""JWT creation and verification, built on PyJWT.

``jwt.decode`` is always called with an explicit ``algorithms`` list. Omitting it
is what enables algorithm-confusion attacks, where an attacker re-signs a token
with ``alg: none`` or swaps HMAC for RSA.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import jwt

from greatapi.conf.settings import get_settings
from greatapi.db.base import utcnow
from greatapi.exceptions import GreatAPIError

__all__ = ["TokenError", "create_token", "decode_token"]


class TokenError(GreatAPIError):
    """A token was missing, malformed, expired or signed with the wrong key."""


def create_token(
    subject: str,
    *,
    token_type: str = "access",  # noqa: S107 - a token kind, not a secret
    expires_in: timedelta | None = None,
    **claims: Any,
) -> str:
    """Sign a JWT for ``subject``.

    Extra keyword arguments become additional claims.
    """
    settings = get_settings()
    issued_at = utcnow()
    lifetime = expires_in or timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        **claims,
        "sub": subject,
        "typ": token_type,
        "iat": issued_at,
        "exp": issued_at + lifetime,
    }
    return jwt.encode(payload, settings.secret_key_value, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, expected_type: str | None = "access") -> dict[str, Any]:
    """Verify a token and return its claims, or raise ``TokenError``."""
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.secret_key_value,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid.") from exc

    if expected_type is not None and payload.get("typ") != expected_type:
        raise TokenError("Token is not valid for this operation.")
    return payload
