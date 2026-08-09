# GreatAPI

**The batteries-included FastAPI framework.** Admin, auth, migrations, jobs and
streaming out of the box — so you ship the backend instead of the plumbing.

```bash
pip install greatapi
greatapi startproject myapp && cd myapp
cp .env.example .env
greatapi migrate && greatapi createsuperuser
greatapi runserver
```

An API on <http://127.0.0.1:8000>, docs at `/docs`, a working admin at `/admin`.

## Why

FastAPI gives you an excellent routing and validation layer and then stops.
Every team builds the same next thing by hand: an admin, a login, Alembic
wiring, a job queue, API keys. GreatAPI is that layer.

It is the same layer whether you are serving a CRUD API or an LLM. The AI
features live behind an extra, and the core install has no LLM dependency at
all.

## What is here

| | |
|---|---|
| [Admin](admin.md) | Real CRUD over any model, with search, pagination and generated forms. No CDN, light and dark, works offline. |
| [Migrations](migrations.md) | Alembic behind `makemigrations` and `migrate`. |
| [Jobs](jobs.md) | A database-backed queue with retries, running in-process. No Redis. |
| [API keys](api-keys.md) | Scopes, rate limits and monthly spend caps. |
| [Streaming](streaming.md) | SSE with heartbeats and proper cancellation. |
| [AI](ai/providers.md) | Providers, agents, and token/cost accounting in the admin. |

## Async, on purpose

An LLM call holds a connection open for anywhere between five seconds and two
minutes. On a synchronous endpoint FastAPI runs each request on a threadpool
worker, so a few dozen concurrent streams exhaust the default pool of forty and
the whole application stalls — the single most common way a FastAPI AI backend
falls over.

GreatAPI is async throughout: SQLAlchemy 2.0 `AsyncSession`, `aiosqlite` by
default, `asyncpg` through the `postgres` extra.

## Installing

```bash
pip install greatapi              # the framework. no LLM dependency
pip install "greatapi[ai]"        # + every provider and the agent tooling
pip install "greatapi[anthropic]" # + one provider
pip install "greatapi[local]"     # + self-hosted models; httpx only
pip install "greatapi[postgres]"  # + asyncpg
pip install "greatapi[all]"       # ai + postgres
```

The AI code ships in the base wheel; only third-party SDKs come from the extras.
`import greatapi.ai` always works, and touching a provider you have not
installed raises a `MissingDependencyError` that names the extra — rather than
an `ImportError` from four frames down.

## Where next

- [Quickstart](quickstart.md) — five minutes
- [Tutorial](tutorial.md) — a streaming AI backend, start to finish
- [Upgrading from 1.x](migration.md)
