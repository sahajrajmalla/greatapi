"""Alembic integration.

Alembic is powerful and its setup is a chore -- an ``alembic.ini``, an
``env.py`` of async boilerplate, and a mental model that is not
``manage.py migrate``. Closing that gap is one of the clearest wins over plain
FastAPI, so GreatAPI generates the scaffolding and drives it behind two
familiar commands::

    greatapi makemigrations -m "add documents"
    greatapi migrate

The generated ``migrations/env.py`` stays about ten lines because the async
plumbing lives here, in the installed package, where it can be fixed by
upgrading rather than by editing every project that ever ran startproject.
"""

from __future__ import annotations

__all__ = ["build_config", "run_migrations"]

from greatapi.db.migrations.runner import build_config, run_migrations
