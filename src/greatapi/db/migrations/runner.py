"""Alembic wiring, shared by the generated ``env.py`` and the CLI."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Literal

from alembic import context
from alembic.config import Config
from sqlalchemy import MetaData, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from greatapi.conf.settings import get_settings
from greatapi.exceptions import ImproperlyConfigured

__all__ = ["build_config", "run_migrations"]

MIGRATIONS_DIRNAME = "migrations"


def build_config(project_root: Path | None = None) -> Config:
    """Build an Alembic config for the project in ``project_root``.

    Constructed in code rather than parsed from alembic.ini, so the database URL
    always comes from GreatAPI settings. Keeping it in two places is how a
    migration ends up applied to the wrong database.
    """
    root = project_root or Path.cwd()
    script_location = root / MIGRATIONS_DIRNAME
    if not script_location.exists():
        raise ImproperlyConfigured(
            f"No {MIGRATIONS_DIRNAME}/ directory in {root}.\n"
            "Run this from your project root, or create one with 'greatapi startproject'."
        )

    config = Config()
    config.set_main_option("script_location", str(script_location))
    # Escaped because ConfigParser treats a bare % as interpolation, and
    # passwords in database URLs are percent-encoded.
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
    return config


def run_migrations(target_metadata: MetaData) -> None:
    """Entry point for the generated ``migrations/env.py``."""
    if context.is_offline_mode():
        _run_offline(target_metadata)
    else:
        asyncio.run(_run_online(target_metadata))


def _configure(connection: Connection | None, target_metadata: MetaData, **extra: Any) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # SQLite cannot ALTER most things, so Alembic emulates it by rebuilding
        # the table. Without this, every column change fails on the default
        # database -- which is the one nearly everyone develops against.
        render_as_batch=True,
        include_object=_include_object,
        render_item=_render_item,
        **extra,
    )


def _render_item(type_: str, obj: Any, autogen_context: Any) -> Literal[False]:
    """Make sure a custom column type's module is imported in the revision.

    Alembic renders a user-defined type by its full dotted path -- for example
    ``greatapi.db.base.UTCDateTime()`` -- but does not add the corresponding
    import, so the generated migration fails with ``NameError`` the first time
    it runs. Registering the import and then returning ``False`` keeps
    Alembic's own rendering and only supplies what it left out.

    This covers application types too, not just GreatAPI's own.
    """
    if type_ == "type":
        module = type(obj).__module__
        if module and not module.startswith("sqlalchemy"):
            autogen_context.imports.add(f"import {module}")
    return False


def _include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    """Leave tables GreatAPI does not own alone.

    Without this, autogenerate proposes dropping anything in the database that
    is not in the metadata -- Alembic's own version table, or tables belonging
    to another service sharing the schema.
    """
    return not (type_ == "table" and reflected and compare_to is None)


def _run_offline(target_metadata: MetaData) -> None:
    _configure(
        None,
        target_metadata,
        url=get_settings().database_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _apply(connection: Connection, target_metadata: MetaData) -> None:
    _configure(connection, target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_online(target_metadata: MetaData) -> None:
    config = context.config
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))

    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_apply, target_metadata)
    finally:
        await engine.dispose()
