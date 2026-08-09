"""Recording what every provider call cost.

This is what makes the admin dashboard real observability rather than a mockup:
each call writes a row with model, tokens, cost, latency and outcome, attributed
to the API key that authorised the request.

Recording uses its own session, never the request's. A usage write must not join
the caller's transaction -- rolling back a failed request would erase the record
of the tokens it already spent.
"""

from __future__ import annotations

import logging

from greatapi.ai.pricing import estimate_cost
from greatapi.ai.types import Usage
from greatapi.db.models import LLMCall, RunStatus
from greatapi.db.session import session_scope

__all__ = ["record_call"]

logger = logging.getLogger("greatapi.ai.usage")


async def record_call(
    *,
    provider: str,
    model: str,
    usage: Usage,
    latency_ms: int,
    operation: str = "complete",
    status: RunStatus = RunStatus.succeeded,
    error: str | None = None,
    agent_run_id: int | None = None,
    cost_usd: float | None = None,
) -> LLMCall | None:
    """Persist one call. Never raises -- telemetry must not break a request."""
    from greatapi.conf.settings import get_settings
    from greatapi.keys.dependencies import current_api_key

    if not get_settings().ai_track_usage:
        return None

    key = current_api_key.get()
    record = LLMCall(
        provider=provider,
        model=model,
        operation=operation,
        status=status,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        cost_usd=cost_usd if cost_usd is not None else estimate_cost(model, usage),
        latency_ms=latency_ms,
        error=error,
        api_key_id=key.id if key is not None else None,
        agent_run_id=agent_run_id,
    )

    try:
        async with session_scope() as session:
            session.add(record)
    except Exception:
        logger.warning("Could not record LLM usage for %s", model, exc_info=True)
        return None
    return record
