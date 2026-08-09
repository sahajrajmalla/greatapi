"""Anthropic adapter. Needs ``pip install "greatapi[anthropic]"``."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from greatapi.ai.providers.base import (
    ProviderError,
    TransientProviderError,
    require,
    split_system,
)
from greatapi.ai.types import Chunk, Completion, Message, ToolCall, ToolSpec, Usage
from greatapi.conf.settings import get_settings

__all__ = ["AnthropicProvider"]

_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
_DEFAULT_MAX_TOKENS = 4096


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str | None = None) -> None:
        self._sdk = require("anthropic", "anthropic", "The Anthropic provider")
        settings = get_settings()
        key = api_key or (
            settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        )
        self._client = self._sdk.AsyncAnthropic(
            api_key=key, timeout=settings.ai_request_timeout_seconds, max_retries=0
        )

    # -- translation ------------------------------------------------------

    def _payload(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None,
        system: str | None,
        temperature: float | None,
        max_tokens: int | None,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        inline_system, conversation = split_system(messages)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [_to_anthropic(message) for message in conversation],
            # Anthropic requires max_tokens; the others default it server-side.
            "max_tokens": max_tokens or _DEFAULT_MAX_TOKENS,
        }
        combined = system or inline_system
        if combined:
            payload["system"] = combined
        if temperature is not None:
            payload["temperature"] = temperature
        if tools:
            payload["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools
            ]
        payload.update(extra)
        return payload

    def _translate_error(self, exc: Exception) -> ProviderError:
        status = getattr(exc, "status_code", None)
        if status is None:
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)

        if isinstance(exc, self._sdk.APIConnectionError | self._sdk.APITimeoutError):
            return TransientProviderError(f"Anthropic connection failed: {exc}", status_code=status)
        if status in _RETRYABLE_STATUS:
            return TransientProviderError(f"Anthropic returned {status}: {exc}", status_code=status)
        return ProviderError(f"Anthropic call failed: {exc}", status_code=status)

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
        payload = self._payload(model, messages, tools, system, temperature, max_tokens, kwargs)
        try:
            response = await self._client.messages.create(**payload)
        except Exception as exc:
            raise self._translate_error(exc) from exc

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=dict(block.input or {}))
                )

        return Completion(
            text="".join(text_parts),
            model=model,
            provider=self.name,
            usage=Usage(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
            ),
            tool_calls=tool_calls,
            finish_reason=response.stop_reason,
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
        payload = self._payload(model, messages, tools, system, temperature, max_tokens, kwargs)
        usage = Usage()
        # Tool arguments arrive as a stream of JSON fragments and are only
        # parseable once the block closes.
        partial: dict[int, dict[str, Any]] = {}

        try:
            async with self._client.messages.stream(**payload) as stream:
                async for event in stream:
                    kind = getattr(event, "type", "")

                    if kind == "content_block_start":
                        block = event.content_block
                        if block.type == "tool_use":
                            partial[event.index] = {"id": block.id, "name": block.name, "json": ""}

                    elif kind == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            yield Chunk(type="text", text=delta.text)
                        elif delta.type == "input_json_delta" and event.index in partial:
                            partial[event.index]["json"] += delta.partial_json

                    elif kind == "content_block_stop" and event.index in partial:
                        pending = partial.pop(event.index)
                        yield Chunk(
                            type="tool_call",
                            tool_call=ToolCall(
                                id=pending["id"],
                                name=pending["name"],
                                arguments=_loads(pending["json"]),
                            ),
                        )

                    elif kind == "message_start":
                        usage.prompt_tokens = event.message.usage.input_tokens

                    elif kind == "message_delta" and getattr(event, "usage", None):
                        usage.completion_tokens = event.usage.output_tokens
        except Exception as exc:
            raise self._translate_error(exc) from exc

        yield Chunk(type="usage", usage=usage)


def _to_anthropic(message: Message) -> dict[str, Any]:
    if message.role == "tool":
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id,
                    "content": message.content,
                }
            ],
        }

    if message.tool_calls:
        content: list[dict[str, Any]] = []
        if message.content:
            content.append({"type": "text", "text": message.content})
        content.extend(
            {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
            for call in message.tool_calls
        )
        return {"role": "assistant", "content": content}

    return {"role": message.role, "content": message.content}


def _loads(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
