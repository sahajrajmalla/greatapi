"""The provider interface."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from greatapi.ai.types import Chunk, Completion, Message, ToolSpec
from greatapi.exceptions import GreatAPIError, MissingDependencyError

__all__ = [
    "Provider",
    "ProviderError",
    "TransientProviderError",
    "require",
]


class ProviderError(GreatAPIError):
    """A provider call failed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TransientProviderError(ProviderError):
    """A failure worth retrying: rate limit, timeout, or a 5xx."""


@runtime_checkable
class Provider(Protocol):
    """What every adapter implements.

    Two methods, both provider-neutral in and out. Adapters own the translation
    to and from their SDK's shapes; nothing above this layer knows the difference.
    """

    name: str

    async def complete(
        self,
        model: str,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Completion: ...

    def stream(
        self,
        model: str,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Chunk]: ...


def require(package: str, extra: str, feature: str) -> Any:
    """Import an optional SDK, or raise an actionable error.

    The alternative -- letting ``ImportError: No module named 'anthropic'``
    escape from four frames deep -- tells the user what is missing but not what
    to do about it.
    """
    import importlib

    try:
        return importlib.import_module(package)
    except ImportError as exc:
        raise MissingDependencyError(package, extra, feature) from exc


def split_system(messages: list[Message]) -> tuple[str | None, list[Message]]:
    """Pull leading system turns out, for APIs that take them separately."""
    system_parts = [m.content for m in messages if m.role == "system"]
    remaining = [m for m in messages if m.role != "system"]
    return ("\n\n".join(system_parts) or None, remaining)
