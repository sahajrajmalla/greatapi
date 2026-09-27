"""Any OpenAI-compatible chat completions endpoint, over plain httpx.

Covers the official OpenAI API and, more usefully, everything that speaks its
protocol: Ollama, vLLM, LM Studio, llama.cpp, Groq, Together, OpenRouter. That
means ``pip install "greatapi[local]"`` -- httpx and nothing else -- is enough to
talk to a self-hosted model, with no vendor SDK anywhere in the dependency tree.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from greatapi.ai.providers.base import ProviderError, TransientProviderError, require
from greatapi.ai.types import Chunk, Completion, Message, ToolCall, ToolSpec, Usage
from greatapi.conf.settings import get_settings

__all__ = ["OpenAICompatibleProvider"]

_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
_DEFAULT_BASE_URL = "http://localhost:11434/v1"


class OpenAICompatibleProvider:
    name = "local"

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self._httpx = require("httpx", "local", "The OpenAI-compatible provider")
        settings = get_settings()
        self.base_url = (base_url or settings.openai_base_url or _DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or (
            settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        )
        self.timeout = settings.ai_request_timeout_seconds

    def _client(self) -> Any:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return self._httpx.AsyncClient(
            base_url=self.base_url, headers=headers, timeout=self.timeout
        )

    def _payload(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None,
        system: str | None,
        temperature: float | None,
        max_tokens: int | None,
        stream: bool,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        conversation = list(messages)
        if system:
            conversation = [Message(role="system", content=system), *conversation]

        payload: dict[str, Any] = {
            "model": model,
            "messages": [_to_openai(message) for message in conversation],
            "stream": stream,
        }
        if stream:
            # Without this, most implementations omit usage from streamed responses.
            payload["stream_options"] = {"include_usage": True}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        payload.update(extra)
        return payload

    def _raise(self, exc: Exception) -> ProviderError:
        if isinstance(exc, self._httpx.TimeoutException | self._httpx.ConnectError):
            return TransientProviderError(f"Could not reach {self.base_url}: {exc}")
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in _RETRYABLE_STATUS:
            return TransientProviderError(f"Endpoint returned {status}: {exc}", status_code=status)
        return ProviderError(f"Request to {self.base_url} failed: {exc}", status_code=status)

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
        payload = self._payload(
            model, messages, tools, system, temperature, max_tokens, False, kwargs
        )
        try:
            async with self._client() as client:
                response = await client.post("/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise self._raise(exc) from exc

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage_data = data.get("usage") or {}

        return Completion(
            text=message.get("content") or "",
            model=data.get("model", model),
            provider=self.name,
            usage=Usage(
                prompt_tokens=int(usage_data.get("prompt_tokens", 0)),
                completion_tokens=int(usage_data.get("completion_tokens", 0)),
            ),
            tool_calls=[_to_tool_call(call) for call in message.get("tool_calls") or []],
            finish_reason=choice.get("finish_reason"),
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
        payload = self._payload(
            model, messages, tools, system, temperature, max_tokens, True, kwargs
        )
        usage = Usage()
        # Tool calls stream in as indexed fragments and only make sense assembled.
        partial: dict[int, dict[str, Any]] = {}

        try:
            async with (
                self._client() as client,
                client.stream("POST", "/chat/completions", json=payload) as response,
            ):
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if not body or body == "[DONE]":
                        continue

                    try:
                        event = json.loads(body)
                    except json.JSONDecodeError:
                        continue

                    if event.get("usage"):
                        usage = Usage(
                            prompt_tokens=int(event["usage"].get("prompt_tokens", 0)),
                            completion_tokens=int(event["usage"].get("completion_tokens", 0)),
                        )

                    for choice in event.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            yield Chunk(type="text", text=delta["content"])
                        for fragment in delta.get("tool_calls") or []:
                            _merge_tool_fragment(partial, fragment)
        except Exception as exc:
            raise self._raise(exc) from exc

        for pending in partial.values():
            yield Chunk(
                type="tool_call",
                tool_call=ToolCall(
                    id=pending.get("id") or "call-0",
                    name=pending.get("name", ""),
                    arguments=_loads(pending.get("arguments", "")),
                ),
            )

        yield Chunk(type="usage", usage=usage)


def _to_openai(message: Message) -> dict[str, Any]:
    if message.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    return payload


def _to_tool_call(raw: dict[str, Any]) -> ToolCall:
    function = raw.get("function") or {}
    return ToolCall(
        id=raw.get("id") or "call-0",
        name=function.get("name", ""),
        arguments=_loads(function.get("arguments", "")),
    )


def _merge_tool_fragment(partial: dict[int, dict[str, Any]], fragment: dict[str, Any]) -> None:
    index = fragment.get("index", 0)
    slot = partial.setdefault(index, {"id": None, "name": "", "arguments": ""})
    if fragment.get("id"):
        slot["id"] = fragment["id"]
    function = fragment.get("function") or {}
    if function.get("name"):
        slot["name"] = function["name"]
    if function.get("arguments"):
        slot["arguments"] += function["arguments"]


def _loads(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
