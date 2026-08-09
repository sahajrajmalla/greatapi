# Settings

Everything is read from the environment, or a `.env` file in the working
directory, prefixed `GREATAPI_`.

```bash
GREATAPI_SECRET_KEY=...
GREATAPI_DATABASE_URL=postgresql+asyncpg://user:pass@localhost/app
GREATAPI_DEBUG=false
```

```python
from greatapi.conf.settings import get_settings

settings = get_settings()
```

## General

| Setting | Default | |
|---|---|---|
| `SECRET_KEY` | *required* | Signs sessions and tokens. `greatapi generate-secret` |
| `DEBUG` | `false` | Developer conveniences. Never on in production |

`SECRET_KEY` has no default. With debug off, a missing one stops the app
starting; with debug on it generates a temporary key and warns, so sessions do
not survive a restart.

## Database

| Setting | Default | |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./greatapi.db` | Any async SQLAlchemy URL |
| `DATABASE_ECHO` | `false` | Log every statement |
| `DATABASE_POOL_SIZE` | `5` | Ignored for SQLite |
| `DATABASE_MAX_OVERFLOW` | `10` | Ignored for SQLite |

## Security

| Setting | Default | |
|---|---|---|
| `JWT_ALGORITHM` | `HS256` | `HS256`, `HS384` or `HS512` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | |
| `SESSION_COOKIE_NAME` | `greatapi_session` | |
| `SESSION_COOKIE_SECURE` | `not DEBUG` | HTTPS-only cookies |
| `SESSION_MAX_AGE_SECONDS` | `43200` | 12 hours |
| `PASSWORD_MIN_LENGTH` | `8` | |
| `LOGIN_RATE_LIMIT_PER_MINUTE` | `10` | Per client address |

## Admin

| Setting | Default | |
|---|---|---|
| `ADMIN_ENABLED` | `true` | |
| `ADMIN_PATH` | `/admin` | Leading and trailing slashes are normalised |
| `ADMIN_TITLE` | `GreatAPI` | Shown in the sidebar and page titles |
| `ADMIN_PAGE_SIZE` | `25` | 1–200 |

## Jobs

| Setting | Default | |
|---|---|---|
| `JOBS_ENABLED` | `true` | Runs the worker in-process |
| `JOBS_WORKER_CONCURRENCY` | `4` | Jobs at a time |
| `JOBS_POLL_INTERVAL_SECONDS` | `1.0` | Only waited when the queue is empty |
| `JOBS_DEFAULT_MAX_ATTEMPTS` | `3` | |

## Streaming

| Setting | Default | |
|---|---|---|
| `SSE_HEARTBEAT_SECONDS` | `15.0` | Keeps idle connections alive |

## AI

| Setting | Default | |
|---|---|---|
| `AI_ENABLED` | auto-detected | Shows the usage pages |
| `AI_DEFAULT_MODEL` | `echo:demo` | Used when no model is passed |
| `AI_REQUEST_TIMEOUT_SECONDS` | `120.0` | |
| `AI_MAX_RETRIES` | `2` | Transient failures only |
| `AI_TRACK_USAGE` | `true` | Records every call |
| `AI_PRICING` | unset | JSON: `{"provider:model": [in, out]}` per million tokens |
| `ANTHROPIC_API_KEY` | unset | |
| `OPENAI_API_KEY` | unset | |
| `OPENAI_BASE_URL` | unset | For `local:`, e.g. `http://localhost:11434/v1` |

## In tests

```python
from greatapi.conf.settings import override_settings

with override_settings(debug=True, ai_default_model="echo:demo"):
    ...
```
