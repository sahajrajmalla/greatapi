# Streaming chat + agent demo

Everything here runs offline against the built-in `echo` provider: no API key,
no network, no cost.

```bash
make seed          # sample data, so the dashboards show something
make demo          # from the repository root
```

or by hand:

```bash
cd examples/chat
GREATAPI_DEBUG=true greatapi runserver --app app:app
```

| URL | What |
|---|---|
| <http://127.0.0.1:8000/> | a browser UI streaming tokens over SSE |
| <http://127.0.0.1:8000/admin> | the admin (sign in with `demo` / `demopassword1`) |
| <http://127.0.0.1:8000/admin/usage> | tokens, cost and latency for what you just ran |
| <http://127.0.0.1:8000/docs> | the OpenAPI docs |

## Point it at a real model

```bash
pip install "greatapi[anthropic]"
export GREATAPI_ANTHROPIC_API_KEY=sk-ant-...
export GREATAPI_AI_DEFAULT_MODEL=anthropic:claude-sonnet-5
```

Or at a local one, with no vendor SDK at all:

```bash
pip install "greatapi[local]"          # httpx only
export GREATAPI_AI_DEFAULT_MODEL=local:llama3.2
export GREATAPI_OPENAI_BASE_URL=http://localhost:11434/v1
```

Nothing else changes.
