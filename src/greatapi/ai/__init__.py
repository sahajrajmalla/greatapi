"""AI backend batteries: providers, streaming, agents and token accounting.

This module always imports. Only the third-party SDKs live in extras, so calling
a provider you have not installed raises a
:class:`~greatapi.exceptions.MissingDependencyError` telling you exactly what to
install -- never a bare ``ImportError`` from four frames down.

::

    pip install "greatapi[ai]"

    from greatapi import ai

    @app.post("/chat")
    async def chat(request: Request, body: ChatIn):
        return ai.sse(ai.stream("anthropic:claude-sonnet-5", body.messages), request=request)

``echo:demo`` works with no extras, no key and no network, so the quickstart and
the test suite run offline.

Streaming, jobs and API keys are re-exported from the core package: they are
useful to any backend, and this keeps AI code to a single import.
"""

from __future__ import annotations

__all__ = [
    "Agent",
    "AgentResult",
    "Chunk",
    "Completion",
    "Message",
    "ModelPrice",
    "Provider",
    "ProviderError",
    "SSEResponse",
    "StreamEvent",
    "Tool",
    "ToolCall",
    "ToolSpec",
    "TransientProviderError",
    "Usage",
    "available_providers",
    "complete",
    "current_api_key",
    "enqueue",
    "estimate_cost",
    "get_provider",
    "job",
    "record_call",
    "register_pricing",
    "register_provider",
    "require_api_key",
    "resolve",
    "sse",
    "stream",
    "tool",
    "unpriced_models",
]

from greatapi.ai.agents import Agent, AgentResult, Tool, tool
from greatapi.ai.client import complete, stream
from greatapi.ai.pricing import ModelPrice, estimate_cost, register_pricing, unpriced_models
from greatapi.ai.providers import (
    Provider,
    ProviderError,
    TransientProviderError,
    available_providers,
    get_provider,
    register_provider,
    resolve,
)
from greatapi.ai.types import Chunk, Completion, Message, ToolCall, ToolSpec, Usage
from greatapi.ai.usage import record_call
from greatapi.jobs import enqueue, job
from greatapi.keys import current_api_key, require_api_key
from greatapi.streaming import SSEResponse, StreamEvent, sse
