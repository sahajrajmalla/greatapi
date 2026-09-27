"""Declarative base and shared column mixins."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, MetaData, TypeDecorator
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "TimestampMixin", "UTCDateTime", "utcnow"]

# Explicit constraint names keep Alembic's autogenerate output stable and let
# SQLite's batch ALTER emulation find constraints by name instead of guessing.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    """Timezone-aware current time. Use this instead of ``datetime.utcnow()``.

    ``datetime.UTC`` is 3.11+, and GreatAPI supports 3.10.
    """
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator[datetime]):
    """A timestamp that is always timezone-aware UTC, on every backend.

    SQLite has no native timestamp type and hands values back naive even for
    ``DateTime(timezone=True)``. Comparing one of those with an aware
    :func:`utcnow` raises ``TypeError: can't compare offset-naive and
    offset-aware datetimes`` -- at runtime, in whichever code path happened to
    load a stored date first.

    Normalising on the way in and on the way out makes SQLite and Postgres
    behave identically, so application code never has to ask which one it is
    talking to.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        stored: datetime = value
        if stored.tzinfo is None:
            return stored.replace(tzinfo=timezone.utc)
        return stored.astimezone(timezone.utc)


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for every model, framework-owned or application-owned."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    def __repr__(self) -> str:
        pk = getattr(self, "id", None)
        return f"<{type(self).__name__} id={pk!r}>"


class TimestampMixin:
    """Adds ``created_at`` / ``updated_at``, maintained by the database."""

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
