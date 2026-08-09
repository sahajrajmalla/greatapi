"""Job handler registration."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from greatapi.exceptions import GreatAPIError

__all__ = [
    "JobHandler",
    "UnknownJobError",
    "clear_registry",
    "get_handler",
    "job",
    "registered_jobs",
]

Handler = Callable[..., Awaitable[Any]]
F = TypeVar("F", bound=Handler)


class UnknownJobError(GreatAPIError):
    """A queued job names a handler this process does not know about."""


@dataclass(frozen=True, slots=True)
class JobHandler:
    name: str
    func: Handler
    max_attempts: int | None


_registry: dict[str, JobHandler] = {}


def job(name: str | None = None, *, max_attempts: int | None = None) -> Callable[[F], F]:
    """Register an async function as a background job.

    ::

        @job("summarize")
        async def summarize(document_id: int) -> str:
            ...

        await enqueue(summarize, document_id=7)
    """

    def decorator(func: F) -> F:
        if not inspect.iscoroutinefunction(func):
            raise TypeError(
                f"Job handler {func.__name__!r} must be an async function. "
                "Blocking work in the worker would stall every other job."
            )
        job_name = name or func.__name__
        if job_name in _registry and _registry[job_name].func is not func:
            raise GreatAPIError(f"A different job is already registered as {job_name!r}.")
        _registry[job_name] = JobHandler(name=job_name, func=func, max_attempts=max_attempts)
        func.__greatapi_job_name__ = job_name  # type: ignore[attr-defined]
        return cast(F, func)

    return decorator


def get_handler(name: str) -> JobHandler:
    try:
        return _registry[name]
    except KeyError:
        raise UnknownJobError(
            f"No job handler registered as {name!r}. "
            "Import the module that defines it before starting the worker."
        ) from None


def registered_jobs() -> dict[str, JobHandler]:
    return dict(_registry)


def clear_registry() -> None:
    _registry.clear()
