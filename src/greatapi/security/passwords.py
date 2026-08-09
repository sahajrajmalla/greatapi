"""Password hashing.

Argon2id is the primary algorithm; bcrypt is kept enabled purely so hashes
written by GreatAPI 1.x still verify. Those get transparently re-hashed to
Argon2 the next time their owner logs in successfully.

This replaces ``passlib``, whose last release predates bcrypt 4.x and which
raises ``AttributeError: module 'bcrypt' has no attribute '__about__'`` against
any current bcrypt.
"""

from __future__ import annotations

import re
from functools import lru_cache

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from greatapi.conf.settings import get_settings

__all__ = [
    "PasswordPolicyError",
    "hash_password",
    "validate_password",
    "verify_password",
]

# A pre-computed hash of a value nobody will guess. Verifying against it when a
# user does not exist keeps the failure path the same cost as a real one, so
# response timing does not reveal whether an account exists.
_DUMMY_PASSWORD = "greatapi-nonexistent-user-placeholder"  # noqa: S105


class PasswordPolicyError(ValueError):
    """Raised when a proposed password fails the configured policy."""


@lru_cache(maxsize=1)
def _hasher() -> PasswordHash:
    return PasswordHash((Argon2Hasher(), BcryptHasher()))


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return _hasher().hash(_DUMMY_PASSWORD)


def hash_password(password: str) -> str:
    """Hash a plaintext password with Argon2id."""
    return _hasher().hash(password)


def verify_password(password: str, hashed: str | None) -> tuple[bool, str | None]:
    """Check a password against a stored hash.

    Returns ``(is_valid, upgraded_hash)``. ``upgraded_hash`` is non-``None`` when
    the stored hash used an older algorithm or cost and should be replaced.

    Passing ``hashed=None`` (no such user) still performs a full verification
    against a dummy hash so the call takes the same time as a real miss.
    """
    if hashed is None:
        _hasher().verify(password, _dummy_hash())
        return False, None
    try:
        return _hasher().verify_and_update(password, hashed)
    except Exception:
        # A corrupt or unrecognised hash is a failed login, not a 500.
        return False, None


def validate_password(password: str) -> None:
    """Enforce the configured password policy, or raise ``PasswordPolicyError``."""
    minimum = get_settings().password_min_length
    if len(password) < minimum:
        raise PasswordPolicyError(f"Password must be at least {minimum} characters long.")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise PasswordPolicyError("Password must contain at least one letter and one digit.")
