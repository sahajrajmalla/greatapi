"""Environment-driven configuration.

Every knob is read from the environment (prefix ``GREATAPI_``) or a ``.env``
file, so nothing security-sensitive has to live in source control::

    GREATAPI_SECRET_KEY=...
    GREATAPI_DATABASE_URL=postgresql+asyncpg://user:pass@localhost/app
"""

from __future__ import annotations

import importlib.util
import secrets
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from greatapi.exceptions import ImproperlyConfigured

__all__ = [
    "ADMIN_STATIC_DIR",
    "ADMIN_TEMPLATE_DIR",
    "PACKAGE_DIR",
    "Settings",
    "get_settings",
    "override_settings",
    "reset_settings",
]

PACKAGE_DIR = Path(__file__).resolve().parent.parent
ADMIN_STATIC_DIR = PACKAGE_DIR / "admin" / "static"
ADMIN_TEMPLATE_DIR = PACKAGE_DIR / "admin" / "templates"


class Settings(BaseSettings):
    """Runtime configuration for a GreatAPI application."""

    model_config = SettingsConfigDict(
        env_prefix="GREATAPI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_default=True,
    )

    # -- General ----------------------------------------------------------
    debug: bool = False
    """Enables developer conveniences. Never enable this in production."""

    secret_key: SecretStr | None = None
    """Signs sessions and tokens. Required unless ``debug`` is on.

    Generate one with ``greatapi generate-secret``.
    """

    # -- Database ---------------------------------------------------------
    database_url: str = "sqlite+aiosqlite:///./greatapi.db"
    """Any SQLAlchemy *async* URL: ``sqlite+aiosqlite://`` or ``postgresql+asyncpg://``."""

    database_echo: bool = False
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)

    # -- Security ---------------------------------------------------------
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = Field(default=60, ge=1)
    session_cookie_name: str = "greatapi_session"
    session_cookie_secure: bool | None = None
    """Defaults to ``not debug`` so local HTTP development works and production does not."""

    session_max_age_seconds: int = Field(default=60 * 60 * 12, ge=60)
    password_min_length: int = Field(default=8, ge=8)
    login_rate_limit_per_minute: int = Field(default=10, ge=1)

    # -- Admin ------------------------------------------------------------
    admin_enabled: bool = True
    admin_path: str = "/admin"
    admin_title: str = "GreatAPI"
    admin_page_size: int = Field(default=25, ge=1, le=200)

    # -- Jobs -------------------------------------------------------------
    jobs_enabled: bool = True
    jobs_worker_concurrency: int = Field(default=4, ge=1)
    jobs_poll_interval_seconds: float = Field(default=1.0, gt=0)
    jobs_default_max_attempts: int = Field(default=3, ge=1)

    # -- Streaming --------------------------------------------------------
    sse_heartbeat_seconds: float = Field(default=15.0, gt=0)

    # -- AI ---------------------------------------------------------------
    ai_enabled: bool | None = None
    """``None`` auto-detects: on when any provider SDK (or httpx) is importable."""

    ai_default_model: str = "echo:demo"
    ai_request_timeout_seconds: float = Field(default=120.0, gt=0)
    ai_max_retries: int = Field(default=2, ge=0)
    ai_track_usage: bool = True

    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None
    """Point at Ollama/vLLM/LM Studio, e.g. ``http://localhost:11434/v1``."""

    @model_validator(mode="after")
    def _resolve_defaults(self) -> Settings:
        if self.secret_key is None:
            if not self.debug:
                raise ImproperlyConfigured(
                    "GREATAPI_SECRET_KEY is not set.\n"
                    "Generate one with:  greatapi generate-secret\n"
                    "then put it in your .env file as GREATAPI_SECRET_KEY=<value>."
                )
            # Debug only: an ephemeral key keeps `greatapi startproject` frictionless,
            # at the cost of invalidating every session on restart.
            object.__setattr__(self, "secret_key", SecretStr(secrets.token_urlsafe(64)))
            warnings.warn(
                "GREATAPI_SECRET_KEY is not set; generated a temporary key because "
                "debug is on. Sessions will not survive a restart and this will "
                "refuse to start with debug off.",
                RuntimeWarning,
                stacklevel=2,
            )

        if self.session_cookie_secure is None:
            object.__setattr__(self, "session_cookie_secure", not self.debug)

        if self.ai_enabled is None:
            object.__setattr__(self, "ai_enabled", _ai_available())

        object.__setattr__(self, "admin_path", "/" + self.admin_path.strip("/"))
        return self

    @property
    def secret_key_value(self) -> str:
        """The signing key as plain text. Never log or render this."""
        assert self.secret_key is not None  # guaranteed by the validator
        return self.secret_key.get_secret_value()

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


def _ai_available() -> bool:
    return any(
        importlib.util.find_spec(name) is not None for name in ("httpx", "anthropic", "openai")
    )


_cached: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide settings, reading the environment on first call."""
    global _cached
    if _cached is None:
        _cached = Settings()
    return _cached


def reset_settings() -> None:
    """Drop the cached settings so the next call re-reads the environment."""
    global _cached
    _cached = None


@contextmanager
def override_settings(**overrides: Any) -> Iterator[Settings]:
    """Temporarily replace the cached settings. Intended for tests.

    ::

        with override_settings(debug=True, database_url="sqlite+aiosqlite://"):
            ...
    """
    global _cached
    previous = _cached
    _cached = get_settings().model_copy(update=overrides)
    try:
        yield _cached
    finally:
        _cached = previous
