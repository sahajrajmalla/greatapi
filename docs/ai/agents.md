# Agents

A bounded tool-calling loop, with every step streamed and recorded.

```python
from greatapi import ai

@ai.tool
async def lookup_order(order_id: int) -> dict:
    """Fetch an order's delivery status by its id."""
    return await orders.get(order_id)

@ai.tool
async def refund(order_id: int, reason: str) -> str:
    """Refund an order. Use only when the customer asks."""
    return await billing.refund(order_id, reason)

support = ai.Agent(
    name="support",
    model="anthropic:claude-sonnet-5",
    tools=[lookup_order, refund],
    system="You are a concise support assistant.",
    max_steps=8,
)
```

```python
result = await support.run("Where is order 4021?")
print(result.output, result.steps, result.usage.total_tokens, result.cost_usd)
```

Or streamed to a browser:

```python
@app.post("/agent")
async def run(request: Request, body: ChatIn):
    return ai.sse(support.stream(body.prompt), request=request)
```

## Tools are ordinary functions

The JSON Schema comes from the signature and the docstring, so there is one
source of truth and no schema to drift:

```python
@ai.tool
async def search(query: str, limit: int = 10) -> list[dict]:
    """Search the product catalogue."""
```

```json
{
  "type": "object",
  "properties": {
    "query": {"type": "string"},
    "limit": {"type": "integer"}
  },
  "required": ["query"]
}
```

Pydantic models, enums and dataclasses are described properly. Sync functions
work too. Name one explicitly if you want:

```python
@ai.tool("catalogue_search", description="Search the catalogue by keyword.")
async def _search(query: str) -> list[dict]: ...
```

## Steps are bounded

`max_steps` is a hard ceiling. A model that keeps calling tools will otherwise
keep spending money until something else stops it, and that something is
usually a billing alert.

When the ceiling is hit the run ends and is recorded as failed with the reason,
rather than silently returning a partial answer.

## A failing tool is not a failing run

An exception inside a tool comes back to the model as text:

```
Error running refund: ValueError: order 4021 is already refunded
```

The model gets the chance to retry with different arguments or explain the
problem to the user, which is usually better than tearing down the run.

## Streamed events

| `type` | When |
|---|---|
| `text` | The model produced prose |
| `tool_call` | The model asked for a tool, with its arguments |
| `step` | A tool returned, with `event: "tool_result"` |
| `usage` | Cumulative tokens for the run |
| `step` | Final, carrying the `AgentResult` |

```javascript
source.addEventListener("tool_call", (e) => {
  const { name, arguments: args } = JSON.parse(e.data).tool_call;
  showSpinner(`Looking up ${args.order_id}…`);
});
```

## Runs are traces

Each run is an `AgentRun` row, and each step is an `LLMCall` linked to it. A
finished run opens in the admin under `/admin/usage` with its steps, tokens,
cost and latency — rather than being a number in a log line.

```python
support = ai.Agent(model="echo:demo", track=False)   # opt out
```

## Metering

Agent runs are expensive. Put one behind a key with a budget:

```python
@app.post("/agent")
async def run(request: Request, body: ChatIn,
              key = Depends(ai.require_api_key("agent:run"))):
    return ai.sse(support.stream(body.prompt), request=request)
```

Spend is attributed to that key, and the request is refused with `402` once the
monthly cap is reached. See [API keys](../api-keys.md).

## Long-running agents

An agent that takes minutes belongs in a [job](../jobs.md), not a request:

```python
@job("run_agent")
async def run_agent(prompt: str) -> str:
    result = await support.run(prompt)
    return result.output
```
