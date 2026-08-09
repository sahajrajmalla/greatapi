"""Provider registry and model-string resolution.

Models are addressed as ``provider:model``::

    echo:demo                     always available, no key, no network
    anthropic:claude-sonnet-5     needs greatapi[anthropic]
    openai:gpt-5                  needs greatapi[openai]
    local:llama3.2                needs greatapi[local]; Ollama/vLLM/LM Studio

Providers are constructed on first use and cached, so importing
:mod:`greatapi.ai` never reaches for an SDK or opens a connection.
"""

from __future__ import annotations

from collections.abc import Callable

from greatapi.ai.providers.base import (
    Provider,
    ProviderError,
    TransientProviderError,
    require,
    split_system,
)
from greatapi.ai.providers.echo import EchoProvider
from greatapi.conf.settings import get_settings
from greatapi.exceptions import GreatAPIError

__all__ = [
    "Provider",
    "ProviderError",
    "TransientProviderError",
    "available_providers",
    "get_provider",
    "register_provider",
    "require",
    "resolve",
    "split_system",
]

_factories: dict[str, Callable[[], Provider]] = {}
_instances: dict[str, Provider] = {}


def register_provider(name: str, factory: Callable[[], Provider]) -> None:
    """Add or replace a provider. Call before first use of its model strings."""
    _factories[name] = factory
    _instances.pop(name, None)


def _register_builtins() -> None:
    register_provider("echo", EchoProvider)

    def _anthropic() -> Provider:
        from greatapi.ai.providers.anthropic import AnthropicProvider

        return AnthropicProvider()

    def _openai() -> Provider:
        from greatapi.ai.providers.openai import OpenAIProvider

        return OpenAIProvider()

    def _local() -> Provider:
        from greatapi.ai.providers.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider()

    register_provider("anthropic", _anthropic)
    register_provider("openai", _openai)
    register_provider("local", _local)


_register_builtins()


def available_providers() -> list[str]:
    return sorted(_factories)


def get_provider(name: str) -> Provider:
    """Return a provider by name, building it on first use."""
    if name not in _factories:
        raise GreatAPIError(
            f"Unknown provider {name!r}. Available: {', '.join(available_providers())}. "
            "Register your own with ai.register_provider(name, factory)."
        )
    if name not in _instances:
        # A MissingDependencyError from here is the intended, actionable failure.
        _instances[name] = _factories[name]()
    return _instances[name]


def resolve(model: str | None = None) -> tuple[Provider, str]:
    """Turn ``"provider:model"`` into a provider instance and the model name."""
    target = model or get_settings().ai_default_model
    if ":" not in target:
        raise GreatAPIError(
            f"Model {target!r} is missing its provider prefix. "
            f"Use one of: {', '.join(f'{name}:...' for name in available_providers())}."
        )
    provider_name, _, model_name = target.partition(":")
    if not model_name:
        raise GreatAPIError(f"Model {target!r} has a provider but no model name.")
    return get_provider(provider_name), model_name


def reset_providers() -> None:
    """Drop cached instances. Used between tests."""
    _instances.clear()
