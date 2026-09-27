<div align="center">

<img src="https://raw.githubusercontent.com/sahajrajmalla/greatapi/master/docs/assets/greatapi-logo.svg" alt="GreatAPI" width="320" />

**The batteries-included FastAPI framework.**
Admin, auth, migrations, jobs and streaming out of the box — so you ship the
backend instead of the plumbing.

[![CI](https://github.com/sahajrajmalla/greatapi/actions/workflows/ci.yml/badge.svg)](https://github.com/sahajrajmalla/greatapi/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/greatapi?color=blue)](https://pypi.org/project/greatapi/)
[![Python](https://img.shields.io/pypi/pyversions/greatapi)](https://pypi.org/project/greatapi/)
[![License](https://img.shields.io/pypi/l/greatapi)](LICENSE)

<img src="https://raw.githubusercontent.com/sahajrajmalla/greatapi/master/docs/assets/admin-dashboard.png" alt="The GreatAPI admin dashboard" width="900" />

</div>

---

FastAPI gives you a superb routing and validation layer and then stops. Every
team builds the same next thing by hand: an admin, a login, Alembic wiring, a
job queue, API keys. GreatAPI is that layer, and it is the same one whether
you are serving a CRUD API or an LLM.

```bash
pip install greatapi
greatapi startproject myapp && cd myapp
cp .env.example .env
greatapi migrate && greatapi createsuperuser
greatapi runserver
```

You now have an API on <http://127.0.0.1:8000>, OpenAPI docs at `/docs`, and a
working admin at `/admin`.

```python
# main.py
from greatapi import GreatAPI

app = GreatAPI(title="myapp", installed_apps=["blog"])
```

```python
# blog/admin.py
from greatapi import admin
from blog.models import Post

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "published", "created_at")
    search_fields = ("title", "body")
```

That is the whole registration. `greatapi startapp blog` writes the model,
schemas, repository, router and admin file, and adds the app to
`INSTALLED_APPS`, so it serves requests and appears in the admin without
another edit.

## What you get

| | |
|---|---|
| **Admin** | Real CRUD over any model, with search, pagination, forms generated from your columns, light/dark, and no CDN. |
| **Auth** | Argon2 passwords, `HttpOnly` sessions, CSRF, and a login that is not an account-enumeration oracle. |
| **Migrations** | Alembic behind `greatapi makemigrations` and `greatapi migrate`. |
| **Jobs** | A database-backed queue with retries and backoff, running in-process. No Redis, no Celery. |
| **API keys** | Scopes, per-key rate limits and monthly spend caps, managed from the admin. |
| **Streaming** | SSE done properly: heartbeats, correct framing, and cancellation when the client leaves. |
| **Async** | SQLAlchemy 2.0 `AsyncSession` throughout, so long-lived connections do not eat a thread each. |

<table>
<tr>
<td width="50%"><a href="https://raw.githubusercontent.com/sahajrajmalla/greatapi/master/docs/assets/admin-ai-usage.png"><img src="https://raw.githubusercontent.com/sahajrajmalla/greatapi/master/docs/assets/admin-ai-usage.png" alt="Tokens, cost and latency per model" /></a><br /><sub><b>AI usage</b> — tokens, cost and latency, recorded on every call</sub></td>
<td width="50%"><a href="https://raw.githubusercontent.com/sahajrajmalla/greatapi/master/docs/assets/admin-jobs.png"><img src="https://raw.githubusercontent.com/sahajrajmalla/greatapi/master/docs/assets/admin-jobs.png" alt="The background job queue" /></a><br /><sub><b>Jobs</b> — a durable queue with retries, right in the admin</sub></td>
</tr>
<tr>
<td width="50%"><a href="https://raw.githubusercontent.com/sahajrajmalla/greatapi/master/docs/assets/admin-api-keys.png"><img src="https://raw.githubusercontent.com/sahajrajmalla/greatapi/master/docs/assets/admin-api-keys.png" alt="API keys with scopes and spend caps" /></a><br /><sub><b>API keys</b> — scopes, rate limits and monthly spend caps</sub></td>
<td width="50%"><a href="https://raw.githubusercontent.com/sahajrajmalla/greatapi/master/docs/assets/admin-llm-calls.png"><img src="https://raw.githubusercontent.com/sahajrajmalla/greatapi/master/docs/assets/admin-llm-calls.png" alt="Sortable list view over any model" /></a><br /><sub><b>List views</b> — search, sort and paginate any model you register</sub></td>
</tr>
</table>

## The AI extra

```bash
pip install "greatapi[ai]"
```

```python
from greatapi import ai

@app.post("/chat")
async def chat(request: Request, body: ChatIn):
    return ai.sse(ai.stream("anthropic:claude-sonnet-5", body.prompt), request=request)
```

```python
@ai.tool
async def lookup_order(order_id: int) -> dict:
    """Fetch an order by its id."""
    ...

agent = ai.Agent(model="anthropic:claude-sonnet-5", tools=[lookup_order], max_steps=8)

@app.post("/agent")
async def run(request: Request, body: ChatIn):
    return ai.sse(agent.stream(body.prompt), request=request)
```

Tool schemas come from your type hints, so there is one source of truth. Every
call and every agent step is recorded with its model, tokens, cost, latency and
outcome, and shows up at `/admin/usage` — an agent run opens as a trace rather
than a number in a log line.

<a href="https://raw.githubusercontent.com/sahajrajmalla/greatapi/master/docs/assets/admin-agent-runs.png"><img src="https://raw.githubusercontent.com/sahajrajmalla/greatapi/master/docs/assets/admin-agent-runs.png" alt="Agent runs, with steps and cost" width="900" /></a>

Models are addressed as `provider:model`:

| String | Needs |
|---|---|
| `echo:demo` | nothing — offline, deterministic, no API key |
| `anthropic:claude-sonnet-5` | `greatapi[anthropic]` |
| `openai:gpt-5` | `greatapi[openai]` |
| `local:llama3.2` | `greatapi[local]` — httpx only; Ollama, vLLM, LM Studio, llama.cpp |

Try it without signing up for anything:

```bash
git clone https://github.com/sahajrajmalla/greatapi && cd greatapi
make install && make demo
```

## Installing

```bash
pip install greatapi              # the framework. no LLM dependency at all
pip install "greatapi[ai]"        # + every provider and the agent tooling
pip install "greatapi[anthropic]" # + one provider
pip install "greatapi[local]"     # + self-hosted models, httpx only
pip install "greatapi[postgres]"  # + asyncpg
```

The AI code ships in the base wheel; only third-party SDKs live in the extras.
`import greatapi.ai` always works, and reaching for a provider you have not
installed tells you exactly what to install rather than raising an `ImportError`
from four frames down.

## Commands

```bash
greatapi startproject <name>          # a project that runs
greatapi startapp <name>              # an app, registered for you
greatapi runserver --port 8000        # the dev server
greatapi makemigrations -m "message"  # a migration from your model changes
greatapi migrate                      # apply them
greatapi createsuperuser              # an admin account
greatapi routes                       # every route in the app
greatapi generate-secret              # a signing key
```

## Configuration

Everything is read from the environment or `.env`, prefixed `GREATAPI_`:

```bash
GREATAPI_SECRET_KEY=...                                  # required; greatapi generate-secret
GREATAPI_DATABASE_URL=postgresql+asyncpg://u:p@host/db    # any async SQLAlchemy URL
GREATAPI_DEBUG=false
```

`SECRET_KEY` has no default. With `DEBUG` off, a missing one stops the app
starting and tells you how to make one.

## Documentation

<https://greatapi.readthedocs.io> — quickstart, tutorial, admin, migrations,
jobs, API keys, AI providers, agents, deployment, and the full settings
reference.

Upgrading from 1.x? See [MIGRATION.md](MIGRATION.md).

## Contributing

```bash
git clone https://github.com/sahajrajmalla/greatapi && cd greatapi
make install
make check       # ruff, mypy, and the test suite
make demo        # see it work
```

Details in [CONTRIBUTING.md](CONTRIBUTING.md). Issues and pull requests are
welcome; good first issues are labelled.

## Security

Please report vulnerabilities privately — see [SECURITY.md](SECURITY.md).

## Credits

Built by [Sahaj Raj Malla](https://github.com/sahajrajmalla).

Standing on [FastAPI](https://fastapi.tiangolo.com),
[Starlette](https://www.starlette.io), [Pydantic](https://docs.pydantic.dev),
[SQLAlchemy](https://www.sqlalchemy.org) and [Alembic](https://alembic.sqlalchemy.org).

MIT licensed.
