# Quickstart

Five minutes, no API key, no database server.

## 1. Install and scaffold

```bash
pip install greatapi
greatapi startproject myapp
cd myapp
cp .env.example .env
```

`.env` already contains a generated `GREATAPI_SECRET_KEY`.

```
myapp/
├── main.py             the application
├── myapp/settings.py   INSTALLED_APPS
├── migrations/         Alembic
├── .env                configuration, git-ignored
└── README.md
```

## 2. Create the schema and an account

```bash
greatapi migrate
greatapi createsuperuser
```

## 3. Run it

```bash
greatapi runserver
```

| | |
|---|---|
| <http://127.0.0.1:8000/> | your API |
| <http://127.0.0.1:8000/docs> | OpenAPI docs |
| <http://127.0.0.1:8000/admin> | the admin |

## 4. Add an app

```bash
greatapi startapp blog
greatapi makemigrations -m "add blog"
greatapi migrate
```

`startapp` writes a working vertical slice — model, schemas, repository, router
and admin registration — and adds `blog` to `INSTALLED_APPS`. Restart the
server: `/blog/items` is serving, and Blog Item is in the admin sidebar.

Try it:

```bash
curl -X POST localhost:8000/blog/items \
  -H 'content-type: application/json' \
  -d '{"title": "Hello", "body": "First post"}'
```

## 5. Stream from a model

```bash
pip install "greatapi[ai]"
```

```python title="main.py"
from fastapi import Request
from greatapi import ai
from pydantic import BaseModel

class ChatIn(BaseModel):
    prompt: str

@app.post("/chat")
async def chat(request: Request, body: ChatIn):
    return ai.sse(ai.stream("echo:demo", body.prompt), request=request)
```

```bash
curl -N localhost:8000/chat -H 'content-type: application/json' -d '{"prompt":"hi"}'
```

`echo:demo` is a built-in offline model, so this works with no key. Point it at
a real one by changing the string:

```bash
export GREATAPI_ANTHROPIC_API_KEY=sk-ant-...
```

```python
ai.stream("anthropic:claude-sonnet-5", body.prompt)
```

Then look at `/admin/usage`: tokens, cost and latency for everything you just
ran.

## Where next

- [Tutorial](tutorial.md) — the same thing, explained
- [Admin](admin.md) — customising what it shows
- [Jobs](jobs.md) — work that outlives the request
