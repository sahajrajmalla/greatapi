"""API keys: issuance, scopes, rate limits and spend caps.

AI backends are consumed machine-to-machine, where a browser session is the
wrong primitive. This is the auth story for that case.
"""

from __future__ import annotations

__all__ = [
    "InMemoryRateLimiter",
    "KeyRejection",
    "RateLimiter",
    "create_api_key",
    "current_api_key",
    "get_rate_limiter",
    "hash_key",
    "monthly_spend",
    "require_api_key",
    "revoke_api_key",
    "set_rate_limiter",
    "verify_api_key",
]

from greatapi.keys.dependencies import current_api_key, require_api_key
from greatapi.keys.ratelimit import (
    InMemoryRateLimiter,
    RateLimiter,
    get_rate_limiter,
    set_rate_limiter,
)
from greatapi.keys.service import (
    KeyRejection,
    create_api_key,
    hash_key,
    monthly_spend,
    revoke_api_key,
    verify_api_key,
)
