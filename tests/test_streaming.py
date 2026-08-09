"""SSE framing, heartbeats and cancellation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest

from greatapi import GreatAPI
from greatapi.streaming import StreamEvent, sse


def frames(body: str) -> list[str]:
    return [block for block in body.split("\n\n") if block.strip()]


class TestFraming:
    def test_plain_string_becomes_a_data_line(self) -> None:
        assert StreamEvent(data="hello").encode() == b"data: hello\n\n"

    def test_multiline_payload_gets_one_data_line_per_line(self) -> None:
        # A bare newline inside the payload would otherwise end the frame early.
        encoded = StreamEvent(data="one\ntwo").encode().decode()
        assert encoded == "data: one\ndata: two\n\n"

    def test_dict_payload_is_json(self) -> None:
        encoded = StreamEvent(data={"a": 1}).encode().decode()
        assert encoded == 'data: {"a": 1}\n\n'

    def test_event_id_and_retry_are_emitted(self) -> None:
        encoded = StreamEvent(data="x", event="token", id="7", retry=3000).encode().decode()
        assert encoded == "event: token\nid: 7\nretry: 3000\ndata: x\n\n"


class TestOverHttp:
    async def _serve(self, source: AsyncIterator[object], **kwargs: object) -> httpx.Response:
        app = GreatAPI(title="sse", admin=False, jobs=False, create_tables=False)

        @app.get("/stream")
        async def stream_endpoint() -> object:
            return sse(source, **kwargs)  # type: ignore[arg-type]

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/stream")

    async def test_headers_defeat_proxy_buffering(self) -> None:
        async def source() -> AsyncIterator[str]:
            yield "a"

        response = await self._serve(source())
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache, no-transform"
        # Without this nginx buffers the whole body and the client sees nothing.
        assert response.headers["x-accel-buffering"] == "no"

    async def test_stream_ends_with_a_done_event(self) -> None:
        async def source() -> AsyncIterator[str]:
            for token in ("one", "two", "three"):
                yield token

        response = await self._serve(source())
        blocks = frames(response.text)
        assert blocks[:3] == ["data: one", "data: two", "data: three"]
        assert blocks[-1] == "event: done\ndata: [DONE]"

    async def test_send_done_can_be_disabled(self) -> None:
        async def source() -> AsyncIterator[str]:
            yield "only"

        response = await self._serve(source(), send_done=False)
        assert "event: done" not in response.text

    async def test_source_error_becomes_an_error_event(self) -> None:
        async def source() -> AsyncIterator[str]:
            yield "partial"
            raise RuntimeError("provider exploded")

        response = await self._serve(source())
        assert "data: partial" in response.text
        assert "event: error" in response.text
        assert "provider exploded" in response.text
        # A failed stream must not also claim to have finished cleanly.
        assert "event: done" not in response.text

    async def test_default_event_name_is_applied(self) -> None:
        async def source() -> AsyncIterator[str]:
            yield "hi"

        response = await self._serve(source(), event="token")
        assert "event: token\ndata: hi" in response.text


class TestHeartbeat:
    async def test_idle_stream_emits_ping_comments(self) -> None:
        async def slow() -> AsyncIterator[str]:
            await asyncio.sleep(0.25)
            yield "finally"

        app = GreatAPI(title="sse", admin=False, jobs=False, create_tables=False)

        @app.get("/stream")
        async def stream_endpoint() -> object:
            return sse(slow(), heartbeat=0.05)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/stream")

        assert ": ping" in response.text, "an idle connection must be kept warm"
        assert "data: finally" in response.text


class TestCancellation:
    async def test_closing_the_response_closes_the_source(self) -> None:
        """An abandoned client must stop the upstream generator.

        Without this an closed browser tab keeps a provider call running, and
        keeps paying for it.
        """
        closed = asyncio.Event()

        async def source() -> AsyncIterator[str]:
            try:
                for index in range(10_000):
                    await asyncio.sleep(0.01)
                    yield f"token-{index}"
            finally:
                closed.set()

        app = GreatAPI(title="sse", admin=False, jobs=False, create_tables=False)

        @app.get("/stream")
        async def stream_endpoint() -> object:
            return sse(source(), heartbeat=5.0)

        transport = httpx.ASGITransport(app=app)
        async with (
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
            client.stream("GET", "/stream") as response,
        ):
            received = 0
            async for _ in response.aiter_lines():
                received += 1
                if received >= 2:
                    break  # walk away mid-stream

        await asyncio.wait_for(closed.wait(), timeout=2.0)
        assert closed.is_set()


class TestChunkShape:
    def test_ai_chunks_serialise_for_the_wire(self) -> None:
        pytest.importorskip("greatapi.ai")
        from greatapi.ai.types import Chunk, ToolCall, Usage

        assert Chunk(type="text", text="hi").to_dict() == {"type": "text", "text": "hi"}

        call = ToolCall(id="1", name="lookup", arguments={"id": 7})
        assert Chunk(type="tool_call", tool_call=call).to_dict()["tool_call"]["name"] == "lookup"

        usage = Chunk(type="usage", usage=Usage(prompt_tokens=3, completion_tokens=4)).to_dict()
        assert usage["usage"]["total_tokens"] == 7
