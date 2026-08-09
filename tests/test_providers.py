"""Provider adapters, driven against a mock HTTP transport.

The OpenAI-compatible adapter is the one that talks to Ollama, vLLM, LM Studio
and every hosted service that speaks the same protocol, so its wire handling is
worth exercising properly -- especially streaming tool calls, which arrive as
indexed fragments that only mean anything once reassembled.
"""

from __future__ import annotations

import json

import httpx
import pytest

from greatapi.ai.providers.base import ProviderError, TransientProviderError, split_system
from greatapi.ai.providers.openai_compatible import OpenAICompatibleProvider
from greatapi.ai.types import Message, ToolSpec


def mock_provider(handler: object) -> OpenAICompatibleProvider:
    """A provider whose HTTP client is backed by ``handler``."""
    provider = OpenAICompatibleProvider(base_url="http://mock/v1", api_key="test")
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    original = provider._client

    def client() -> httpx.AsyncClient:
        real = original()
        real._transport = transport
        return real

    provider._client = client  # type: ignore[method-assign]
    return provider


def sse_body(*events: dict[str, object]) -> str:
    lines = [f"data: {json.dumps(event)}" for event in events]
    lines.append("data: [DONE]")
    return "\n\n".join(lines) + "\n\n"


class TestSystemPrompts:
    def test_leading_system_turns_are_extracted(self) -> None:
        system, rest = split_system(
            [
                Message(role="system", content="be terse"),
                Message(role="system", content="be kind"),
                Message(role="user", content="hi"),
            ]
        )
        assert system == "be terse\n\nbe kind"
        assert [m.role for m in rest] == ["user"]

    def test_no_system_turn(self) -> None:
        system, rest = split_system([Message(role="user", content="hi")])
        assert system is None
        assert len(rest) == 1


class TestComplete:
    async def test_a_normal_response_is_translated(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(
                200,
                json={
                    "model": "llama3.2",
                    "choices": [{"message": {"content": "Hello there"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 7},
                },
            )

        provider = mock_provider(handler)
        result = await provider.complete(
            "llama3.2", [Message(role="user", content="hi")], system="be terse", temperature=0.2
        )

        assert result.text == "Hello there"
        assert result.usage.prompt_tokens == 11
        assert result.usage.completion_tokens == 7
        assert result.finish_reason == "stop"

        body = captured["body"]
        assert body["model"] == "llama3.2"  # type: ignore[index]
        assert body["messages"][0] == {"role": "system", "content": "be terse"}  # type: ignore[index]
        assert body["temperature"] == 0.2  # type: ignore[index]
        assert captured["auth"] == "Bearer test"

    async def test_tools_are_sent_in_openai_shape(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        provider = mock_provider(handler)
        await provider.complete(
            "m",
            [Message(role="user", content="hi")],
            tools=[ToolSpec(name="lookup", description="Look up.", parameters={"type": "object"})],
        )

        tool = captured["body"]["tools"][0]  # type: ignore[index]
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "lookup"

    async def test_a_tool_call_response_is_parsed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "function": {
                                            "name": "lookup",
                                            "arguments": '{"order_id": 42}',
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                },
            )

        result = await mock_provider(handler).complete("m", [Message(role="user", content="hi")])
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "lookup"
        assert result.tool_calls[0].arguments == {"order_id": 42}

    @pytest.mark.parametrize("status", [429, 500, 502, 503])
    async def test_retryable_statuses_become_transient_errors(self, status: int) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json={"error": "busy"})

        with pytest.raises(TransientProviderError):
            await mock_provider(handler).complete("m", [Message(role="user", content="hi")])

    @pytest.mark.parametrize("status", [400, 401, 403, 404])
    async def test_permanent_statuses_are_not_transient(self, status: int) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json={"error": "nope"})

        with pytest.raises(ProviderError) as caught:
            await mock_provider(handler).complete("m", [Message(role="user", content="hi")])
        assert not isinstance(caught.value, TransientProviderError)

    async def test_a_connection_failure_is_transient(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        with pytest.raises(TransientProviderError, match="Could not reach"):
            await mock_provider(handler).complete("m", [Message(role="user", content="hi")])


class TestStreaming:
    async def test_text_deltas_and_usage(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert json.loads(request.content)["stream"] is True
            return httpx.Response(
                200,
                text=sse_body(
                    {"choices": [{"delta": {"content": "Hel"}}]},
                    {"choices": [{"delta": {"content": "lo"}}]},
                    {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}},
                ),
                headers={"content-type": "text/event-stream"},
            )

        chunks = [
            chunk
            async for chunk in mock_provider(handler).stream(
                "m", [Message(role="user", content="hi")]
            )
        ]

        text = "".join(c.text for c in chunks if c.type == "text")
        assert text == "Hello"

        usage = [c for c in chunks if c.type == "usage"]
        assert usage and usage[0].usage is not None
        assert usage[0].usage.total_tokens == 7

    async def test_usage_is_requested_explicitly(self) -> None:
        """Most implementations omit usage from a stream unless asked."""
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, text=sse_body({"choices": []}))

        async for _ in mock_provider(handler).stream("m", [Message(role="user", content="x")]):
            pass

        assert captured["body"]["stream_options"] == {"include_usage": True}  # type: ignore[index]

    async def test_fragmented_tool_calls_are_reassembled(self) -> None:
        """Arguments arrive as partial JSON across several frames."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                text=sse_body(
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": "call_9",
                                            "function": {"name": "lookup", "arguments": '{"or'},
                                        }
                                    ]
                                }
                            }
                        ]
                    },
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {"index": 0, "function": {"arguments": 'der_id": 7}'}}
                                    ]
                                }
                            }
                        ]
                    },
                ),
            )

        chunks = [
            chunk
            async for chunk in mock_provider(handler).stream(
                "m", [Message(role="user", content="hi")]
            )
        ]

        calls = [c.tool_call for c in chunks if c.type == "tool_call"]
        assert len(calls) == 1
        assert calls[0] is not None
        assert calls[0].id == "call_9"
        assert calls[0].name == "lookup"
        assert calls[0].arguments == {"order_id": 7}

    async def test_malformed_json_frames_are_skipped(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                text=(
                    "data: not-json\n\n"
                    'data: {"choices": [{"delta": {"content": "fine"}}]}\n\n'
                    "data: [DONE]\n\n"
                ),
            )

        chunks = [
            chunk
            async for chunk in mock_provider(handler).stream(
                "m", [Message(role="user", content="hi")]
            )
        ]
        assert "".join(c.text for c in chunks if c.type == "text") == "fine"

    async def test_a_streaming_error_is_classified(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": "overloaded"})

        with pytest.raises(TransientProviderError):
            async for _ in mock_provider(handler).stream("m", [Message(role="user", content="x")]):
                pass


class TestMessageTranslation:
    async def test_tool_results_use_the_tool_role(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        await mock_provider(handler).complete(
            "m",
            [
                Message(role="user", content="where is order 7"),
                Message(role="tool", content='{"status": "shipped"}', tool_call_id="call_1"),
            ],
        )

        tool_message = captured["body"]["messages"][1]  # type: ignore[index]
        assert tool_message["role"] == "tool"
        assert tool_message["tool_call_id"] == "call_1"


class TestDefaults:
    def test_it_points_at_ollama_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from greatapi.conf.settings import override_settings

        with override_settings(openai_base_url=None):
            assert OpenAICompatibleProvider().base_url == "http://localhost:11434/v1"

    def test_a_configured_base_url_wins(self) -> None:
        from greatapi.conf.settings import override_settings

        with override_settings(openai_base_url="http://vllm.internal:8000/v1"):
            assert OpenAICompatibleProvider().base_url == "http://vllm.internal:8000/v1"

    def test_a_trailing_slash_is_trimmed(self) -> None:
        assert OpenAICompatibleProvider(base_url="http://x/v1/").base_url == "http://x/v1"
