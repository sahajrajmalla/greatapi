"""Application loading.

The 1.x ``startapp`` generated four files containing one import line each and
registered none of them: you then hand-edited ``main.py`` next to a
``# add custom router`` comment.

Here, listing an app in ``INSTALLED_APPS`` is enough. Each app is imported by
convention:

===================  =========================================================
``<app>/models.py``  imported so its tables reach ``Base.metadata``, which is
                     what makes ``greatapi makemigrations`` see them
``<app>/admin.py``   imported so its ``@admin.register`` calls run
``<app>/router.py``  its module-level ``router`` is included in the app
===================  =========================================================

Missing files are fine -- an app with only models is a perfectly good app.
"""

from __future__ import annotations

import importlib
import logging
from types import ModuleType
from typing import TYPE_CHECKING

from greatapi.exceptions import GreatAPIError

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = ["load_admin", "load_apps", "load_models", "load_routers"]

logger = logging.getLogger("greatapi.apps")

MODELS_MODULE = "models"
ADMIN_MODULE = "admin"
ROUTER_MODULE = "router"


def _import_optional(app: str, submodule: str) -> ModuleType | None:
    """Import ``<app>.<submodule>``, returning None when it does not exist.

    A genuine error *inside* the module is re-raised: silently swallowing it
    would turn a typo in the user's code into a mysteriously absent route.
    """
    dotted = f"{app}.{submodule}"
    try:
        return importlib.import_module(dotted)
    except ModuleNotFoundError as exc:
        if exc.name in (dotted, app):
            if exc.name == app:
                raise GreatAPIError(
                    f"App {app!r} is listed in INSTALLED_APPS but cannot be imported. "
                    "Check the name, and that you are running from the project root."
                ) from exc
            return None
        raise


def load_models(apps: list[str]) -> None:
    """Import every app's models, so Alembic and create_all can see them."""
    for app in apps:
        _import_optional(app, MODELS_MODULE)


def load_admin(apps: list[str]) -> None:
    for app in apps:
        _import_optional(app, ADMIN_MODULE)


def load_routers(apps: list[str], application: FastAPI) -> list[str]:
    """Include each app's ``router``. Returns the apps that provided one."""
    included: list[str] = []
    for app in apps:
        module = _import_optional(app, ROUTER_MODULE)
        if module is None:
            continue
        router = getattr(module, "router", None)
        if router is None:
            logger.warning(
                "%s.%s exists but defines no `router`, so nothing was mounted for %r.",
                app,
                ROUTER_MODULE,
                app,
            )
            continue
        application.include_router(router)
        included.append(app)
    return included


def load_apps(apps: list[str], application: FastAPI | None = None) -> None:
    """Load models, admin and routers for every installed app, in that order."""
    load_models(apps)
    load_admin(apps)
    if application is not None:
        load_routers(apps, application)
