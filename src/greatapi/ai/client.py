"""The calling surface: :func:`complete` and :func:`stream`.

Both wrap a provider with the things every production caller needs and nobody
enjoys writing twice: a timeout, bounded retries with jittered backoff, and a
usage record written on the way out -- success or failure.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import AsyncIterator
from typing import Any

from greatapi.ai.pricing import estimate_cost
from greatapi.ai.providers import ProviderError, TransientProviderError, resolve
from greatapi.ai.types import Chunk, Completion, Message, ToolSpec, Usage, normalise_messages
from greatapi.ai.usage import record_call
from greatapi.conf.settings import get_settings
from greatapi.db.models import RunStatus

__all__ = ["complete", "stream"]

logger = logging.getLogger("greatapi.ai")

_BASE_BACKOFF_SECONDS = 0.5
_MAX_BACKOFF_SECONDS = 8.0


def _backoff(attempt: int) -> float:
    """Exponential with full jitter, so retries from many workers do not sync up."""
    ceiling = min(_BASE_BACKOFF_SECONDS * 2**attempt, _MAX_BACKOFF_SECONDS)
    return random.uniform(0, ceiling)  # noqa: S311 - jitter, not cryptography


async def complete(
    model: str | None = None,
    messages: str | Message | list[Message] | list[dict[str, Any]] = "",
    *,
    tools: list[ToolSpec] | None = None,
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
    agent_run_id: int | None = None,
    **kwargs: Any,
) -> Completion:
    """Call a model and wait for the whole response.

    ::

        result = await ai.complete("echo:demo", "Say hello")
        print(result.text, result.usage.total_tokens, result.cost_usd)
    """
    settings = get_settings()
    provider, model_name = resolve(model)
    conversation = normalise_messages(messages)
    attempts = settings.ai_max_retries if max_retries is None else max_retries
    deadline = timeout or settings.ai_request_timeout_seconds

    started = time.perf_counter()
    last_error: Exception | None = None

    for attempt in range(attempts + 1):
        try:
            result = await asyncio.wait_for(
                provider.complete(
                    model_name,
                    conversation,
                    tools=tools,
                    system=system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                ),
                timeout=deadline,
            )
        # asyncio.TimeoutError, not the builtin: identical only from 3.11.
        except (TransientProviderError, asyncio.TimeoutError) as exc:
            last_error = exc
            if attempt >= attempts:
                break
            delay = _backoff(attempt)
            logger.warning(
                "Transient failure from %s (%s); retry %s/%s in %.2fs",
                model_name,
                exc,
                attempt + 1,
                attempts,
                delay,
            )
            await asyncio.sleep(delay)
        except Exception as exc:
            last_error = exc
            break
        else:
            latency_ms = int((time.perf_counter() - started) * 1000)
            result.latency_ms = latency_ms
            result.cost_usd = estimate_cost(f"{provider.name}:{model_name}", result.usage)
            await record_call(
                provider=provider.name,
                model=f"{provider.name}:{model_name}",
                usage=result.usage,
                latency_ms=latency_ms,
                operation="complete",
                cost_usd=result.cost_usd,
                agent_run_id=agent_run_id,
            )
            return result

    latency_ms = int((time.perf_counter() - started) * 1000)
    await record_call(
        provider=provider.name,
        model=f"{provider.name}:{model_name}",
        usage=Usage(),
        latency_ms=latency_ms,
        operation="complete",
        status=RunStatus.failed,
        error=str(last_error),
        agent_run_id=agent_run_id,
    )
    if isinstance(last_error, ProviderError):
        raise last_error
    raise ProviderError(f"Call to {model_name} failed: {last_error}") from last_error


async def stream(
    model: str | None = None,
    messages: str | Message | list[Message] | list[dict[str, Any]] = "",
    *,
    tools: list[ToolSpec] | None = None,
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
    agent_run_id: int | None = None,
    **kwargs: Any,
) -> AsyncIterator[Chunk]:
    """Stream a response chunk by chunk.

    ::

        @app.post("/chat")
        async def chat(request: Request, body: ChatIn):
            return sse(ai.stream("echo:demo", body.messages), request=request)

    Retries only apply *before* the first chunk reaches the caller. Once any
    output has been emitted, retrying would duplicate what the client already
    has, so failures propagate instead.
    """
    settings = get_settings()
    provider, model_name = resolve(model)
    conversation = normalise_messages(messages)
    attempts = settings.ai_max_retries if max_retries is None else max_retries
    qualified = f"{provider.name}:{model_name}"

    started = time.perf_counter()
    usage = Usage()
    emitted = False
    # BaseException, not Exception: CancelledError is how a disconnect arrives.
    failure: BaseException | None = None

    try:
        for attempt in range(attempts + 1):
            iterator = provider.stream(
                model_name,
                conversation,
                tools=tools,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            try:
                async for chunk in iterator:
                    emitted = True
                    if chunk.type == "usage" and chunk.usage is not None:
                        usage = chunk.usage
                        continue
                    yield chunk
            # asyncio.TimeoutError, not the builtin: identical only from 3.11.
            except (TransientProviderError, asyncio.TimeoutError) as exc:
                await _aclose(iterator)
                if emitted or attempt >= attempts:
                    failure = exc
                    raise
                delay = _backoff(attempt)
                logger.warning(
                    "Transient failure starting stream from %s (%s); retry %s/%s in %.2fs",
                    model_name,
                    exc,
                    attempt + 1,
                    attempts,
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            except Exception as exc:
                failure = exc
                await _aclose(iterator)
                raise
            else:
                return
    except asyncio.CancelledError:
        # The client hung up. Record what was spent before re-raising.
        failure = failure or asyncio.CancelledError("client disconnected")
        raise
    finally:
        await record_call(
            provider=provider.name,
            model=qualified,
            usage=usage,
            latency_ms=int((time.perf_counter() - started) * 1000),
            operation="stream",
            status=RunStatus.failed if failure is not None else RunStatus.succeeded,
            error=str(failure) if failure is not None else None,
            agent_run_id=agent_run_id,
        )


async def _aclose(iterator: Any) -> None:
    aclose = getattr(iterator, "aclose", None)
    if aclose is None:
        return
    try:
        await aclose()
    except Exception:
        logger.debug("Error closing provider stream", exc_info=True)
