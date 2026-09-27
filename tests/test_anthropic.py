"""The Anthropic adapter's translation layer, against a stand-in client.

The SDK object is replaced rather than the network, because what is worth
testing here is the mapping between Anthropic's block-structured messages and
GreatAPI's provider-neutral types -- particularly streaming tool calls, whose
arguments arrive as partial JSON that is only parseable once the block closes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("anthropic")

from greatapi.ai.providers.anthropic import AnthropicProvider
from greatapi.ai.providers.base import ProviderError, TransientProviderError
from greatapi.ai.types import Message, ToolSpec


def block(kind: str, **fields: Any) -> SimpleNamespace:
    return SimpleNamespace(type=kind, **fields)


@dataclass
class FakeMessages:
    """Stands in for ``client.messages``."""

    response: Any = None
    events: list[Any] = field(default_factory=list)
    error: Exception | None = None
    captured: dict[str, Any] = field(default_factory=dict)

    async def create(self, **payload: Any) -> Any:
        self.captured.update(payload)
        if self.error is not None:
            raise self.error
        return self.response

    def stream(self, **payload: Any) -> Any:
        self.captured.update(payload)
        events, error = self.events, self.error

        class Stream:
            async def __aenter__(self) -> Stream:
                if error is not None:
                    raise error
                return self

            async def __aexit__(self, *exc: object) -> None:
                return None

            async def __aiter__(self) -> AsyncIterator[Any]:
                for event in events:
                    yield event

        return Stream()


def provider_with(messages: FakeMessages) -> AnthropicProvider:
    provider = AnthropicProvider(api_key="test")
    provider._client = SimpleNamespace(messages=messages)  # type: ignore[assignment]
    return provider


class TestComplete:
    async def test_text_and_usage_are_translated(self) -> None:
        messages = FakeMessages(
            response=SimpleNamespace(
                content=[block("text", text="Hello there")],
                usage=SimpleNamespace(input_tokens=12, output_tokens=4),
                stop_reason="end_turn",
            )
        )
        result = await provider_with(messages).complete(
            "claude-sonnet-5", [Message(role="user", content="hi")]
        )

        assert result.text == "Hello there"
        assert result.usage.prompt_tokens == 12
        assert result.usage.completion_tokens == 4
        assert result.finish_reason == "end_turn"

    async def test_max_tokens_is_always_sent(self) -> None:
        """Anthropic requires it; the other providers default it server-side."""
        messages = FakeMessages(
            response=SimpleNamespace(
                content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=1), stop_reason=None
            )
        )
        await provider_with(messages).complete("m", [Message(role="user", content="hi")])
        assert messages.captured["max_tokens"] > 0

    async def test_the_system_prompt_is_hoisted_out_of_the_turns(self) -> None:
        messages = FakeMessages(
            response=SimpleNamespace(
                content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=1), stop_reason=None
            )
        )
        await provider_with(messages).complete(
            "m",
            [
                Message(role="system", content="be terse"),
                Message(role="user", content="hi"),
            ],
        )

        assert messages.captured["system"] == "be terse"
        assert [m["role"] for m in messages.captured["messages"]] == ["user"]

    async def test_tools_use_the_input_schema_key(self) -> None:
        messages = FakeMessages(
            response=SimpleNamespace(
                content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=1), stop_reason=None
            )
        )
        await provider_with(messages).complete(
            "m",
            [Message(role="user", content="hi")],
            tools=[ToolSpec(name="lookup", description="Look up.", parameters={"type": "object"})],
        )

        tool = messages.captured["tools"][0]
        assert tool["name"] == "lookup"
        assert tool["input_schema"] == {"type": "object"}

    async def test_tool_use_blocks_become_tool_calls(self) -> None:
        messages = FakeMessages(
            response=SimpleNamespace(
                content=[
                    block("text", text="Let me check. "),
                    block("tool_use", id="tu_1", name="lookup", input={"order_id": 7}),
                ],
                usage=SimpleNamespace(input_tokens=9, output_tokens=3),
                stop_reason="tool_use",
            )
        )
        result = await provider_with(messages).complete("m", [Message(role="user", content="hi")])

        assert result.text == "Let me check. "
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "lookup"
        assert result.tool_calls[0].arguments == {"order_id": 7}

    async def test_a_tool_result_turn_is_translated(self) -> None:
        messages = FakeMessages(
            response=SimpleNamespace(
                content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=1), stop_reason=None
            )
        )
        await provider_with(messages).complete(
            "m",
            [
                Message(role="user", content="where is order 7"),
                Message(role="tool", content='{"status": "shipped"}', tool_call_id="tu_1"),
            ],
        )

        translated = messages.captured["messages"][1]
        assert translated["role"] == "user"
        assert translated["content"][0]["type"] == "tool_result"
        assert translated["content"][0]["tool_use_id"] == "tu_1"

    async def test_errors_are_classified(self) -> None:
        import anthropic

        transient = FakeMessages(error=_api_error(anthropic, 429))
        with pytest.raises(TransientProviderError):
            await provider_with(transient).complete("m", [Message(role="user", content="hi")])

        permanent = FakeMessages(error=_api_error(anthropic, 400))
        with pytest.raises(ProviderError) as caught:
            await provider_with(permanent).complete("m", [Message(role="user", content="hi")])
        assert not isinstance(caught.value, TransientProviderError)


class TestStreaming:
    async def test_text_deltas_and_usage(self) -> None:
        events = [
            SimpleNamespace(
                type="message_start",
                message=SimpleNamespace(usage=SimpleNamespace(input_tokens=15)),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=0,
                delta=SimpleNamespace(type="text_delta", text="Hel"),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=0,
                delta=SimpleNamespace(type="text_delta", text="lo"),
            ),
            SimpleNamespace(type="message_delta", usage=SimpleNamespace(output_tokens=6)),
        ]

        chunks = [
            chunk
            async for chunk in provider_with(FakeMessages(events=events)).stream(
                "m", [Message(role="user", content="hi")]
            )
        ]

        assert "".join(c.text for c in chunks if c.type == "text") == "Hello"

        usage = next(c for c in chunks if c.type == "usage").usage
        assert usage is not None
        assert usage.prompt_tokens == 15
        assert usage.completion_tokens == 6

    async def test_streamed_tool_arguments_are_assembled(self) -> None:
        events = [
            SimpleNamespace(
                type="content_block_start",
                index=0,
                content_block=block("tool_use", id="tu_9", name="lookup"),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=0,
                delta=SimpleNamespace(type="input_json_delta", partial_json='{"order'),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=0,
                delta=SimpleNamespace(type="input_json_delta", partial_json='_id": 7}'),
            ),
            SimpleNamespace(type="content_block_stop", index=0),
        ]

        chunks = [
            chunk
            async for chunk in provider_with(FakeMessages(events=events)).stream(
                "m", [Message(role="user", content="hi")]
            )
        ]

        calls = [c.tool_call for c in chunks if c.type == "tool_call"]
        assert len(calls) == 1
        assert calls[0] is not None
        assert calls[0].id == "tu_9"
        assert calls[0].arguments == {"order_id": 7}

    async def test_incomplete_json_degrades_to_an_empty_mapping(self) -> None:
        events = [
            SimpleNamespace(
                type="content_block_start",
                index=0,
                content_block=block("tool_use", id="tu_1", name="lookup"),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=0,
                delta=SimpleNamespace(type="input_json_delta", partial_json='{"trunc'),
            ),
            SimpleNamespace(type="content_block_stop", index=0),
        ]

        chunks = [
            chunk
            async for chunk in provider_with(FakeMessages(events=events)).stream(
                "m", [Message(role="user", content="hi")]
            )
        ]
        call = next(c.tool_call for c in chunks if c.type == "tool_call")
        assert call is not None and call.arguments == {}


def _api_error(anthropic_module: Any, status: int) -> Exception:
    """An SDK-shaped error carrying a status code."""

    class FakeAPIError(Exception):
        def __init__(self) -> None:
            super().__init__(f"status {status}")
            self.status_code = status

    return FakeAPIError()
