"""Route table introspection for ``greatapi routes``."""

from __future__ import annotations

import importlib
from typing import Any

from greatapi.exceptions import GreatAPIError

__all__ = ["describe_routes", "import_app"]


def import_app(target: str) -> Any:
    """Import an ASGI app from a ``module:attribute`` string."""
    if ":" not in target:
        raise GreatAPIError(f"Expected 'module:attribute', got {target!r}.")
    module_name, _, attribute = target.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise GreatAPIError(
            f"Could not import {module_name!r}: {exc}. Run this from your project root."
        ) from exc
    try:
        return getattr(module, attribute)
    except AttributeError as exc:
        raise GreatAPIError(f"{module_name!r} has no attribute {attribute!r}.") from exc


def describe_routes(target: str) -> list[tuple[str, str, str]]:
    """Return ``(methods, path, name)`` for every route, sorted by path.

    Recent FastAPI keeps included routers nested rather than flattening them
    into ``app.routes``, so this walks the tree instead of iterating one level.
    """
    application = import_app(target)
    collected: list[tuple[str, str, str]] = []
    _walk(application.routes, "", collected)
    return sorted(collected, key=lambda row: (row[1], row[0]))


def _walk(routes: list[Any], prefix: str, collected: list[tuple[str, str, str]]) -> None:
    for route in routes:
        if type(route).__name__ == "_IncludedRouter":
            context = getattr(route, "include_context", None)
            inner = getattr(route, "original_router", None)
            if inner is not None:
                _walk(inner.routes, prefix + getattr(context, "prefix", ""), collected)
            continue

        path = getattr(route, "path", None)
        if path is None:
            continue
        methods = ",".join(sorted(getattr(route, "methods", None) or ["MOUNT"]))
        name = getattr(route, "name", "") or ""
        collected.append((methods, f"{prefix}{path}", name))
