# Providers

```bash
pip install "greatapi[ai]"
```

Models are addressed as `provider:model`:

| String | Needs | Notes |
|---|---|---|
| `echo:demo` | nothing | Offline, deterministic, no key. Used by the docs and the test suite |
| `anthropic:claude-sonnet-5` | `greatapi[anthropic]` | |
| `openai:gpt-5` | `greatapi[openai]` | |
| `local:llama3.2` | `greatapi[local]` | Any OpenAI-compatible endpoint |

```python
from greatapi import ai

result = await ai.complete("anthropic:claude-sonnet-5", "Say hello")
print(result.text, result.usage.total_tokens, result.cost_usd)

async for chunk in ai.stream("anthropic:claude-sonnet-5", "Say hello"):
    print(chunk.text, end="")
```

Set a default and drop the first argument:

```bash
GREATAPI_AI_DEFAULT_MODEL=anthropic:claude-sonnet-5
```

```python
await ai.complete(messages="Say hello")
```

## Credentials

```bash
GREATAPI_ANTHROPIC_API_KEY=sk-ant-...
GREATAPI_OPENAI_API_KEY=sk-...
GREATAPI_OPENAI_BASE_URL=http://localhost:11434/v1   # for local:
```

## Local and self-hosted models

`greatapi[local]` pulls in httpx and nothing else, and speaks the OpenAI
protocol — so Ollama, vLLM, LM Studio, llama.cpp, Groq, Together and OpenRouter
all work with no vendor SDK anywhere in your dependency tree.

=== "Ollama"

    ```bash
    GREATAPI_AI_DEFAULT_MODEL=local:llama3.2
    GREATAPI_OPENAI_BASE_URL=http://localhost:11434/v1
    ```

=== "vLLM"

    ```bash
    GREATAPI_AI_DEFAULT_MODEL=local:meta-llama/Llama-3.1-8B-Instruct
    GREATAPI_OPENAI_BASE_URL=http://localhost:8000/v1
    ```

=== "LM Studio"

    ```bash
    GREATAPI_AI_DEFAULT_MODEL=local:your-model
    GREATAPI_OPENAI_BASE_URL=http://localhost:1234/v1
    ```

## Timeouts and retries

Every call gets a timeout and bounded retries with exponential backoff and full
jitter. Only transient failures are retried — timeouts, connection errors, and
429 or 5xx responses. A 400 is not retried three times.

```bash
GREATAPI_AI_REQUEST_TIMEOUT_SECONDS=120
GREATAPI_AI_MAX_RETRIES=2
```

```python
await ai.complete("openai:gpt-5", prompt, timeout=30, max_retries=0)
```

Streaming retries only *before* the first chunk reaches the caller. Once output
has been emitted, retrying would duplicate what the client already has, so
failures propagate instead.

## Testing without a network

`echo:demo` replays the prompt back, streaming word by word, so a UI behaves
exactly as it will against a real model. It also understands three markers, for
driving error paths in tests:

| In the prompt | What happens |
|---|---|
| `__fail__` | A permanent `ProviderError` — not retried |
| `__transient__` | A `TransientProviderError` — retried |
| `__tool__` | Calls the first tool it is offered, once |

## Writing your own

```python
from greatapi.ai.providers import register_provider
from greatapi.ai.types import Chunk, Completion, Message, Usage

class MyProvider:
    name = "myvendor"

    async def complete(self, model, messages, *, tools=None, system=None,
                       temperature=None, max_tokens=None, **kwargs) -> Completion:
        ...

    async def stream(self, model, messages, **kwargs):
        yield Chunk(type="text", text="...")
        yield Chunk(type="usage", usage=Usage(prompt_tokens=10, completion_tokens=5))

register_provider("myvendor", MyProvider)
```

Then `myvendor:whatever` works everywhere, including in the usage dashboard.
