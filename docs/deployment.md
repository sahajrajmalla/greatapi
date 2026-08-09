# Deployment

## The checklist

- [ ] `GREATAPI_SECRET_KEY` set from `greatapi generate-secret`, out of source control
- [ ] `GREATAPI_DEBUG` unset or `false`
- [ ] `GREATAPI_DATABASE_URL` pointing at Postgres
- [ ] `greatapi migrate` runs as part of the deploy, before the new code serves
- [ ] HTTPS terminated in front of the app
- [ ] Admin behind a VPN, an IP allow-list or an authenticating proxy, if you can
- [ ] Pricing registered, if you want cost figures
- [ ] Streaming routes exempted from proxy buffering

## Running it

```bash
pip install "greatapi[ai,postgres]"
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

`greatapi runserver` is for development. In production run uvicorn directly, so
your process manager owns restarts and signals.

Workers are processes, so with more than one:

- the in-process job worker runs in *each* of them. That is safe — claiming is
  atomic — but if you want exactly one, set `GREATAPI_JOBS_ENABLED=false` and
  run a [separate worker](jobs.md#running-workers-separately)
- the default rate limiter counts per process. For a hard global ceiling,
  supply a [shared limiter](api-keys.md#rate-limiting-across-processes)

## Docker

```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
RUN pip install "greatapi[ai,postgres]"

COPY . .

# Never bake a secret into an image. Pass it at run time.
ENV GREATAPI_DEBUG=false

EXPOSE 8000
CMD ["sh", "-c", "greatapi migrate && uvicorn main:app --host 0.0.0.0 --port 8000"]
```

```bash
docker run -p 8000:8000 \
  -e GREATAPI_SECRET_KEY="$SECRET" \
  -e GREATAPI_DATABASE_URL="postgresql+asyncpg://..." \
  myapp
```

## nginx

Streaming needs buffering off, and a read timeout longer than your longest
generation:

```nginx
upstream app { server 127.0.0.1:8000; }

server {
    listen 443 ssl http2;
    server_name api.example.com;

    location / {
        proxy_pass http://app;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /chat {
        proxy_pass http://app;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
```

GreatAPI already sends `X-Accel-Buffering: no` on SSE responses, which nginx
honours — but the explicit block covers other proxies too.

## Health checks

The generated project exposes `/health`. It answers as soon as the process is
up; if you want readiness to depend on the database, add your own:

```python
from sqlalchemy import text
from greatapi.security import DbSession

@app.get("/ready")
async def ready(session: DbSession) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}
```

## Migrations during a deploy

Run `greatapi migrate` once, before the new code starts serving — not from every
worker on boot. On Kubernetes that is an init container or a Job; on a PaaS it
is the release phase.

Prefer additive migrations so old and new code can run side by side during a
rolling deploy: add a nullable column, deploy, backfill, then make it required
in a later release.

## Logging

Standard `logging`, under `greatapi`, `greatapi.jobs`, `greatapi.ai`,
`greatapi.streaming`.

```python
import logging
logging.getLogger("greatapi.ai").setLevel(logging.DEBUG)
```

Prompts and completions are never logged, and never stored — only counts, cost
and latency.

## What GreatAPI already does

Every response carries `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: same-origin` and
`Cross-Origin-Opener-Policy: same-origin`. Admin responses additionally carry a
strict `Content-Security-Policy` with no `unsafe-inline`, which is possible
because no admin asset comes from a CDN.
