"""A deterministic offline provider.

Not a toy: it is the reason the quickstart, ``examples/`` and the entire test
suite run with no API key, no network and no cost. A framework you cannot try
without first signing up for something is a framework most people never try.

It streams word by word with a small delay, so streaming UIs behave exactly as
they will against a real model, and it can be told to call a tool or to fail on
demand so error paths are testable.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from greatapi.ai.providers.base import ProviderError, TransientProviderError
from greatapi.ai.types import Chunk, Completion, Message, ToolCall, ToolSpec, Usage

__all__ = ["EchoProvider"]

#: Roughly the ratio real tokenizers land on for English prose. Good enough to
#: make the usage dashboard meaningful without pulling in a tokenizer.
_CHARS_PER_TOKEN = 4


class EchoProvider:
    """Replays the prompt back, deterministically."""

    name = "echo"

    def __init__(self, *, delay: float = 0.01) -> None:
        self.delay = delay

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _count(text: str) -> int:
        return max(1, len(text) // _CHARS_PER_TOKEN)

    @staticmethod
    def _prompt_text(messages: list[Message]) -> str:
        return "\n".join(m.content for m in messages if m.content)

    def _reply(self, messages: list[Message], model: str) -> str:
        prompt = self._prompt_text(messages)
        if not prompt:
            return "Hello from the GreatAPI echo provider."

        # A stable pseudo-id makes assertions in tests easy and output realistic.
        digest = hashlib.sha256(f"{model}:{prompt}".encode()).hexdigest()[:8]
        last = next((m.content for m in reversed(messages) if m.role == "user"), prompt)
        return (
            f"You said: {last.strip()} "
            f"(echoed by {model}, trace {digest}). "
            "Swap the model string for a real provider when you are ready."
        )

    def _control(self, messages: list[Message]) -> str | None:
        """Test hooks: a prompt containing these words drives a specific path."""
        text = self._prompt_text(messages).lower()
        for marker in ("__fail__", "__transient__"):
            if marker in text:
                return marker
        # Ask for a tool only until one has run, so an agent loop does what a
        # real one does -- call the tool, read the result, then answer -- rather
        # than requesting it forever and hitting max_steps.
        if "__tool__" in text and not any(m.role == "tool" for m in messages):
            return "__tool__"
        return None

    # -- interface --------------------------------------------------------

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
    ) -> Completion:
        control = self._control(messages)
        if control == "__fail__":
            raise ProviderError("Echo provider was asked to fail.", status_code=400)
        if control == "__transient__":
            raise TransientProviderError("Echo provider rate limit.", status_code=429)

        await asyncio.sleep(self.delay)

        tool_calls: list[ToolCall] = []
        if control == "__tool__" and tools:
            spec = tools[0]
            tool_calls.append(
                ToolCall(id="echo-call-1", name=spec.name, arguments=_sample_arguments(spec))
            )
            text = ""
        else:
            text = self._reply(messages, model)

        prompt_text = self._prompt_text(messages) + (system or "")
        usage = Usage(
            prompt_tokens=self._count(prompt_text),
            completion_tokens=self._count(text) if text else 1,
        )
        return Completion(
            text=text,
            model=model,
            provider=self.name,
            usage=usage,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
        )

    async def stream(
        self,
        model: str,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Chunk]:
        result = await self.complete(
            model, messages, tools=tools, system=system, max_tokens=max_tokens, **kwargs
        )

        for call in result.tool_calls:
            yield Chunk(type="tool_call", tool_call=call)

        for piece in re.findall(r"\S+\s*", result.text):
            await asyncio.sleep(self.delay)
            yield Chunk(type="text", text=piece)

        yield Chunk(type="usage", usage=result.usage)


def _sample_arguments(spec: ToolSpec) -> dict[str, Any]:
    """Plausible arguments derived from the tool's own JSON Schema."""
    properties = spec.parameters.get("properties", {})
    arguments: dict[str, Any] = {}
    for key, schema in properties.items():
        kind = schema.get("type", "string")
        arguments[key] = {
            "integer": 1,
            "number": 1.0,
            "boolean": True,
            "array": [],
            "object": {},
        }.get(kind, f"sample-{key}")
    # Round-trip so the sample is guaranteed JSON-serialisable, like a real call.
    validated: dict[str, Any] = json.loads(json.dumps(arguments))
    return validated
