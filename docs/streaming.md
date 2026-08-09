# Streaming

Server-Sent Events, done properly. SSE is the right transport for token
streaming: it is plain HTTP, it survives proxies that mangle WebSockets, and
browsers get reconnection for free through `EventSource`.

```python
from fastapi import Request
from greatapi.streaming import sse

@app.post("/chat")
async def chat(request: Request, body: ChatIn):
    return sse(ai.stream("anthropic:claude-sonnet-5", body.prompt), request=request)
```

## What it handles for you

**Framing.** A newline inside a payload would end the frame early, so every line
gets its own `data:` prefix and the client rejoins them.

**Termination.** The stream ends with `event: done` / `data: [DONE]`, matching
the convention the major provider APIs use, so browser code written against
them works unchanged. If the source raises, you get `event: error` instead —
never both.

**Heartbeats.** A `: ping` comment every 15 seconds by default, so an idle
connection is not reaped by a load balancer that considers it dead.

**Proxy buffering.** `X-Accel-Buffering: no` and `Cache-Control: no-cache,
no-transform`. Without the first, nginx buffers the whole response and the
client sees nothing until the stream ends — the classic "it works locally"
streaming bug.

**Cancellation.** Pass `request` and the source is closed as soon as the client
disconnects, so a closed browser tab stops burning provider tokens. Without it
cancellation still happens, but only when the server next notices the broken
pipe.

## Yielding

```python
async def source():
    yield "plain text"              # -> data: plain text
    yield {"token": "hi"}           # -> data: {"token": "hi"}
    yield StreamEvent(              # full control
        data={"n": 1}, event="progress", id="7", retry=3000
    )
```

Anything with a `type` attribute and a `to_dict()` method — such as
`greatapi.ai.Chunk` — is serialised as JSON and named after its type, so a
browser can subscribe per kind:

```javascript
const source = new EventSource("/chat");
source.addEventListener("text", (e) => append(JSON.parse(e.data).text));
source.addEventListener("tool_call", (e) => showTool(JSON.parse(e.data)));
source.addEventListener("done", () => source.close());
```

## Options

```python
sse(
    source,
    request=request,      # cancel promptly on disconnect
    heartbeat=15.0,       # seconds; default from GREATAPI_SSE_HEARTBEAT_SECONDS
    event="token",        # name every frame
    send_done=True,       # emit the terminal done event
)
```

## Consuming it with fetch

`EventSource` cannot issue a POST. For a POST, read the body yourself:

```javascript
const response = await fetch("/chat", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ prompt }),
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });

  const frames = buffer.split("\n\n");
  buffer = frames.pop();
  for (const frame of frames) {
    // frame is `event: <name>` plus one or more `data:` lines
  }
}
```

A complete implementation is in `examples/chat/index.html`.

## Behind a proxy

nginx needs to be told not to buffer, and to allow a long read:

```nginx
location /chat {
    proxy_pass http://app;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 300s;
    proxy_set_header Connection "";
    proxy_http_version 1.1;
}
```

Cloudflare buffers by default on the free plan; SSE needs it disabled for the
route.
