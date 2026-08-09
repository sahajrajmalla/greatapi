# Tutorial

We will build a document service: upload text, summarise it with a model, serve
the result. It exercises models, the admin, streaming, jobs and API keys — the
whole framework, in about twenty minutes.

Everything here runs against the offline `echo` provider, so you need no API key.

## 1. The project

```bash
pip install "greatapi[ai]"
greatapi startproject docs_service && cd docs_service
cp .env.example .env
greatapi startapp documents
```

`startapp` already added `documents` to `INSTALLED_APPS`.

## 2. A model

```python title="documents/models.py"
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from greatapi.db import Base, TimestampMixin

class Document(TimestampMixin, Base):
    __tablename__ = "documents_document"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    body: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
```

```bash
greatapi makemigrations -m "add documents"
greatapi migrate
```

## 3. In the admin

```python title="documents/admin.py"
from greatapi import admin
from documents.models import Document

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "created_at")
    search_fields = ("title", "body")
    readonly_fields = ("created_at", "updated_at")
    ordering = "-created_at"
```

```bash
greatapi createsuperuser
greatapi runserver
```

<http://127.0.0.1:8000/admin> — Document is in the sidebar, with search,
pagination and an edit form built from your columns.

## 4. Endpoints

```python title="documents/schemas.py"
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class DocumentIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)

class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    summary: str | None
    created_at: datetime
```

```python title="documents/router.py"
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from greatapi.security import DbSession
from documents.models import Document
from documents.schemas import DocumentIn, DocumentOut

router = APIRouter(prefix="/documents", tags=["Documents"])

@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def create(payload: DocumentIn, session: DbSession) -> Document:
    document = Document(**payload.model_dump())
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document

@router.get("", response_model=list[DocumentOut])
async def index(session: DbSession) -> list[Document]:
    result = await session.execute(select(Document).order_by(Document.created_at.desc()))
    return list(result.scalars())
```

Note `DocumentIn` and `DocumentOut` are separate. Server-owned fields like `id`
and `created_at` must never be settable by a client.

```bash
curl -X POST localhost:8000/documents \
  -H 'content-type: application/json' \
  -d '{"title": "Async Python", "body": "Coroutines let you..."}'
```

## 5. Streaming a summary

```python title="documents/router.py"
from fastapi import Request
from greatapi import ai

@router.post("/{document_id}/summarise")
async def summarise(document_id: int, request: Request, session: DbSession):
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document.")

    return ai.sse(
        ai.stream(messages=f"Summarise in two sentences:\n\n{document.body}"),
        request=request,
    )
```

```bash
curl -N -X POST localhost:8000/documents/1/summarise
```

Tokens arrive as they are generated. Close the connection and the model call
stops — an abandoned tab costs nothing.

## 6. Doing it in the background instead

Streaming suits a UI. For a batch, queue it:

```python title="documents/jobs.py"
from greatapi import ai
from greatapi.db.session import session_scope
from greatapi.jobs import job

from documents.models import Document

@job("summarise_document", max_attempts=3)
async def summarise_document(document_id: int) -> str:
    async with session_scope() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return "gone"

        result = await ai.complete(messages=f"Summarise: {document.body}")
        document.summary = result.text
        return result.text
```

```python title="documents/router.py"
from greatapi.jobs import enqueue
from documents.jobs import summarise_document

@router.post("/{document_id}/summarise-async")
async def summarise_async(document_id: int) -> dict[str, object]:
    queued = await enqueue(summarise_document, document_id=document_id)
    return {"job_id": queued.id, "poll": f"/jobs/{queued.id}"}
```

Import it so the handler registers:

```python title="documents/__init__.py"
from documents import jobs  # noqa: F401
```

```bash
curl -X POST localhost:8000/documents/1/summarise-async
curl localhost:8000/jobs/1
```

`/admin/jobs` shows the queue, with retry and cancel.

## 7. Metering it

```bash
greatapi runserver
```

At <http://127.0.0.1:8000/admin/api-keys>, create a key with scope
`documents:write`, a rate limit of 60/min and a $10 budget. Copy the plaintext —
it is shown once, because only its hash is stored.

```python
from fastapi import Depends
from greatapi.keys import require_api_key

@router.post("/{document_id}/summarise")
async def summarise(document_id: int, request: Request, session: DbSession,
                    key = Depends(require_api_key("documents:write"))):
    ...
```

```bash
curl -N -X POST localhost:8000/documents/1/summarise -H 'X-API-Key: gapi_...'
```

Without the key: `401`. With the wrong scope: `403`. Over the limit: `429` with
`Retry-After`. Over budget: `402`.

## 8. What it cost

<http://127.0.0.1:8000/admin/usage> — calls, tokens, cost, latency, a per-day
chart and a per-model breakdown.

Cost shows `$0.00` until you say what you pay:

```python title="main.py"
from greatapi import ai

ai.register_pricing("anthropic:claude-sonnet-5", input_per_1m=3.00, output_per_1m=15.00)
```

## 9. A real model

```bash
export GREATAPI_ANTHROPIC_API_KEY=sk-ant-...
export GREATAPI_AI_DEFAULT_MODEL=anthropic:claude-sonnet-5
```

Nothing in your code changes.

## Where next

- [Agents](ai/agents.md) — when the model needs to call your functions
- [Deployment](deployment.md)
