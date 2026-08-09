"""Provider-neutral request and response types.

Every provider adapter converts to and from these, so swapping
``anthropic:...`` for ``openai:...`` or a local model is a string change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = [
    "Chunk",
    "Completion",
    "Message",
    "Role",
    "ToolCall",
    "ToolSpec",
    "Usage",
    "normalise_messages",
]

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True)
class ToolCall:
    """A model's request to invoke a tool."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "arguments": self.arguments}


@dataclass(slots=True)
class Message:
    """One turn of a conversation."""

    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            payload["tool_calls"] = [call.to_dict() for call in self.tool_calls]
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        if self.name:
            payload["name"] = self.name
        return payload


@dataclass(slots=True)
class ToolSpec:
    """A callable exposed to the model, described by a JSON Schema."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(slots=True)
class Usage:
    """Token counts for one call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
        )


@dataclass(slots=True)
class Completion:
    """A finished, non-streamed response."""

    text: str
    model: str
    provider: str
    usage: Usage = field(default_factory=Usage)
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    latency_ms: int = 0
    cost_usd: float = 0.0

    def as_message(self) -> Message:
        return Message(role="assistant", content=self.text, tool_calls=list(self.tool_calls))


ChunkType = Literal["text", "tool_call", "usage", "step", "error"]


@dataclass(slots=True)
class Chunk:
    """One piece of a streamed response.

    Yielded straight into :func:`greatapi.streaming.sse`, where ``type`` becomes
    the SSE event name so a browser can listen per kind::

        source.addEventListener("text", ...)
        source.addEventListener("tool_call", ...)
    """

    type: ChunkType = "text"
    text: str = ""
    tool_call: ToolCall | None = None
    usage: Usage | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": self.type}
        if self.text:
            payload["text"] = self.text
        if self.tool_call is not None:
            payload["tool_call"] = self.tool_call.to_dict()
        if self.usage is not None:
            payload["usage"] = {
                "prompt_tokens": self.usage.prompt_tokens,
                "completion_tokens": self.usage.completion_tokens,
                "total_tokens": self.usage.total_tokens,
            }
        if self.detail:
            payload.update(self.detail)
        return payload


def normalise_messages(
    messages: str | Message | list[Message] | list[dict[str, Any]],
) -> list[Message]:
    """Accept a prompt string, a message, or a list of either shape."""
    if isinstance(messages, str):
        return [Message(role="user", content=messages)]
    if isinstance(messages, Message):
        return [messages]

    result: list[Message] = []
    for item in messages:
        if isinstance(item, Message):
            result.append(item)
        elif isinstance(item, dict):
            result.append(
                Message(
                    role=item.get("role", "user"),
                    content=_stringify(item.get("content", "")),
                    tool_call_id=item.get("tool_call_id"),
                    name=item.get("name"),
                )
            )
        else:
            raise TypeError(f"Cannot interpret {item!r} as a message.")
    return result


def _stringify(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Multimodal blocks: keep the text parts, which is what a text model needs.
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "".join(parts) if parts else json.dumps(content, default=str)
    return json.dumps(content, default=str)
