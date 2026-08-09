"""Server-Sent Events.

SSE is the right transport for token streaming: it is plain HTTP, it survives
proxies that mangle WebSockets, and browsers get reconnection for free via
``EventSource``. The fiddly parts are always the same, so they live here:

* correct framing, including multi-line payloads
* a terminal ``done`` event, and an ``error`` event when the source blows up
* periodic heartbeats so idle connections are not reaped by an intermediary
* ``X-Accel-Buffering: no``, without which nginx buffers the whole response and
  the client sees nothing until the stream ends
* cancelling the source when the client goes away, so an abandoned browser tab
  stops burning provider tokens
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from typing import Any

from starlette.requests import Request
from starlette.responses import StreamingResponse

from greatapi.conf.settings import get_settings

__all__ = ["SSEResponse", "StreamEvent", "sse"]

logger = logging.getLogger("greatapi.streaming")

#: Emitted after the source is exhausted. Mirrors the convention used by the
#: major provider APIs, so browser code written against them works unchanged.
DONE_PAYLOAD = "[DONE]"

_DISCONNECT_POLL_SECONDS = 0.5


@dataclass(slots=True)
class StreamEvent:
    """One SSE frame."""

    data: Any
    event: str | None = None
    id: str | None = None
    retry: int | None = None

    def encode(self) -> bytes:
        lines: list[str] = []
        if self.event is not None:
            lines.append(f"event: {self.event}")
        if self.id is not None:
            lines.append(f"id: {self.id}")
        if self.retry is not None:
            lines.append(f"retry: {self.retry}")

        payload = self.data if isinstance(self.data, str) else json.dumps(self.data, default=str)
        # A bare newline would terminate the frame, so every line gets its own
        # `data:` prefix and the client rejoins them.
        lines.extend(f"data: {line}" for line in payload.split("\n"))
        return ("\n".join(lines) + "\n\n").encode()


class SSEResponse(StreamingResponse):
    """A ``StreamingResponse`` pre-configured for Server-Sent Events."""

    media_type = "text/event-stream"

    def __init__(self, content: AsyncIterable[bytes], **kwargs: Any) -> None:
        headers = {
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            **(kwargs.pop("headers", None) or {}),
        }
        super().__init__(content, headers=headers, media_type=self.media_type, **kwargs)


def sse(
    source: AsyncIterable[Any],
    *,
    request: Request | None = None,
    heartbeat: float | None = None,
    event: str | None = None,
    send_done: bool = True,
) -> SSEResponse:
    """Stream ``source`` to the client as Server-Sent Events.

    ``source`` may yield :class:`StreamEvent` instances for full control, or
    plain values -- strings are sent verbatim, anything else as JSON.

    Pass ``request`` to have the stream cancelled promptly when the client
    disconnects. Without it, cancellation still happens, but only once the
    server notices the broken pipe on its next write.

    ::

        @app.post("/chat")
        async def chat(request: Request, body: ChatIn):
            return sse(ai.stream("echo:demo", body.messages), request=request)
    """
    interval = heartbeat if heartbeat is not None else get_settings().sse_heartbeat_seconds
    return SSEResponse(
        _pump(source, request=request, heartbeat=interval, default_event=event, send_done=send_done)
    )


async def _pump(
    source: AsyncIterable[Any],
    *,
    request: Request | None,
    heartbeat: float,
    default_event: str | None,
    send_done: bool,
) -> AsyncIterator[bytes]:
    iterator = source.__aiter__()
    pending: asyncio.Task[Any] = asyncio.ensure_future(_anext(iterator))
    watcher: asyncio.Task[None] | None = (
        asyncio.ensure_future(_watch_disconnect(request)) if request is not None else None
    )

    try:
        while True:
            waiting: set[asyncio.Task[Any]] = {pending}
            if watcher is not None:
                waiting.add(watcher)

            done, _ = await asyncio.wait(
                waiting, timeout=heartbeat, return_when=asyncio.FIRST_COMPLETED
            )

            if not done:
                # Nothing produced in `heartbeat` seconds: keep the pipe warm.
                yield b": ping\n\n"
                continue

            if watcher is not None and watcher in done:
                logger.debug("SSE client disconnected; cancelling source")
                return

            try:
                item = pending.result()
            except _EndOfStream:
                break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("SSE source raised")
                yield StreamEvent(data={"error": str(exc)}, event="error").encode()
                return

            yield _as_event(item, default_event).encode()
            pending = asyncio.ensure_future(_anext(iterator))

        if send_done:
            yield StreamEvent(data=DONE_PAYLOAD, event="done").encode()
    finally:
        for task in (pending, watcher):
            if task is not None and not task.done():
                task.cancel()
        # Closing the source is what actually stops an in-flight provider call.
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:
                logger.debug("Error closing SSE source", exc_info=True)


class _EndOfStream(Exception):  # noqa: N818 - internal control-flow sentinel
    """Internal: distinguishes exhaustion from a source error inside a Task."""


async def _anext(iterator: AsyncIterator[Any]) -> Any:
    try:
        return await iterator.__anext__()
    except StopAsyncIteration:
        raise _EndOfStream from None


async def _watch_disconnect(request: Request) -> None:
    while True:
        try:
            if await request.is_disconnected():
                return
        except Exception:
            return
        await asyncio.sleep(_DISCONNECT_POLL_SECONDS)


def _as_event(item: Any, default_event: str | None) -> StreamEvent:
    if isinstance(item, StreamEvent):
        if item.event is None and default_event is not None:
            item.event = default_event
        return item
    return StreamEvent(data=item, event=default_event)
