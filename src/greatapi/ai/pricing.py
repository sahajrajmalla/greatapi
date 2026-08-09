"""Cost calculation.

GreatAPI deliberately ships **no** prices for real provider models. Published
rates change, differ by region and contract, and a framework quietly reporting a
number that is 30% wrong is worse than one reporting nothing -- you would build
budgets and alerts on it.

So token counts, latency and call volume work out of the box, and cost activates
the moment you tell it what you pay::

    from greatapi import ai

    ai.register_pricing("anthropic:claude-sonnet-5", input_per_1m=3.00, output_per_1m=15.00)
    ai.register_pricing("openai:gpt-5", input_per_1m=1.25, output_per_1m=10.00)

Prices can also come from the environment as JSON, which suits containers::

    GREATAPI_AI_PRICING='{"anthropic:claude-sonnet-5": [3.0, 15.0]}'
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from greatapi.ai.types import Usage

__all__ = [
    "ModelPrice",
    "estimate_cost",
    "get_pricing",
    "is_priced",
    "register_pricing",
    "unpriced_models",
]

logger = logging.getLogger("greatapi.ai.pricing")

_PRICING_ENV_VAR = "GREATAPI_AI_PRICING"


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """USD per one million tokens."""

    input_per_1m: float
    output_per_1m: float

    def cost(self, usage: Usage) -> float:
        return (
            usage.prompt_tokens * self.input_per_1m + usage.completion_tokens * self.output_per_1m
        ) / 1_000_000


# The echo provider is priced so the quickstart and the admin dashboard show a
# working cost column without anybody having to configure anything.
_pricing: dict[str, ModelPrice] = {
    "echo:demo": ModelPrice(input_per_1m=1.00, output_per_1m=5.00),
}

_unpriced: set[str] = set()
_loaded_env = False


def register_pricing(model: str, *, input_per_1m: float, output_per_1m: float) -> None:
    """Set what you pay for a model, in USD per million tokens."""
    _pricing[model] = ModelPrice(input_per_1m=input_per_1m, output_per_1m=output_per_1m)
    _unpriced.discard(model)


def get_pricing(model: str) -> ModelPrice | None:
    _load_env_pricing()
    if model in _pricing:
        return _pricing[model]
    # `anthropic:claude-sonnet-5` also matches a bare `claude-sonnet-5` entry.
    if ":" in model:
        bare = model.split(":", 1)[1]
        if bare in _pricing:
            return _pricing[bare]
    return None


def is_priced(model: str) -> bool:
    return get_pricing(model) is not None


def estimate_cost(model: str, usage: Usage) -> float:
    """Cost in USD, or ``0.0`` when the model has no registered price."""
    price = get_pricing(model)
    if price is None:
        if model not in _unpriced:
            _unpriced.add(model)
            logger.info(
                "No price registered for %r, so cost is recorded as 0. Set one with "
                "ai.register_pricing(%r, input_per_1m=..., output_per_1m=...)",
                model,
                model,
            )
        return 0.0
    return price.cost(usage)


def unpriced_models() -> set[str]:
    """Models seen at runtime with no registered price. Surfaced in the admin."""
    return set(_unpriced)


def _load_env_pricing() -> None:
    global _loaded_env
    if _loaded_env:
        return
    _loaded_env = True

    raw = os.environ.get(_PRICING_ENV_VAR)
    if not raw:
        return
    try:
        parsed = json.loads(raw)
        for model, value in parsed.items():
            input_price, output_price = value
            _pricing[model] = ModelPrice(
                input_per_1m=float(input_price), output_per_1m=float(output_price)
            )
    except Exception:
        logger.warning(
            'Ignoring %s: expected JSON like {"provider:model": [input_per_1m, output_per_1m]}',
            _PRICING_ENV_VAR,
        )
