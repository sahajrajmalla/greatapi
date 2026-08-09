"""A streaming chat and agent backend in one file.

Runs offline against the built-in ``echo`` provider, so there is nothing to sign
up for. Swap ``GREATAPI_AI_DEFAULT_MODEL`` for ``anthropic:claude-sonnet-5`` or
``local:llama3.2`` and nothing else changes.

    greatapi runserver --app app:app
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from starlette.responses import Response

from greatapi import GreatAPI, admin, ai
from greatapi.conf.settings import get_settings
from greatapi.db import Base, TimestampMixin
from greatapi.jobs import enqueue, job
from greatapi.security import DbSession

HERE = __file__.rsplit("/", 1)[0]


# --------------------------------------------------------------- models


class Conversation(TimestampMixin, Base):
    """One exchange, kept so the admin has something real to show."""

    __tablename__ = "demo_conversation"

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt: Mapped[str] = mapped_column(Text)
    reply: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(120))


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    app_label = "demo"
    list_display = ("id", "prompt", "model", "created_at")
    search_fields = ("prompt", "reply")
    readonly_fields = ("created_at", "updated_at")
    ordering = "-created_at"


# --------------------------------------------------------------- tools


@ai.tool
async def current_time() -> str:
    """The current UTC time, ISO-8601."""
    return datetime.now().isoformat(timespec="seconds")


@ai.tool
async def lookup_order(order_id: int) -> dict[str, object]:
    """Look up an order's delivery status by its id."""
    await asyncio.sleep(0.1)  # stands in for a database or an upstream service
    return {"order_id": order_id, "status": "shipped", "carrier": "DHL", "eta_days": 2}


support_agent = ai.Agent(
    name="support",
    tools=[current_time, lookup_order],
    system="You are a concise customer support assistant. Use the tools you are given.",
    max_steps=6,
)


# --------------------------------------------------------------- jobs


@job("summarise_conversation")
async def summarise_conversation(conversation_id: int) -> str:
    """A slow task that outlives the request that asked for it."""
    from greatapi.db.session import session_scope

    async with session_scope() as session:
        record = await session.get(Conversation, conversation_id)
        if record is None:
            return "gone"
        result = await ai.complete(messages=f"Summarise in one line: {record.prompt}")
        return result.text


# --------------------------------------------------------------- app

app = GreatAPI(title="GreatAPI chat demo", version="1.0.0")


class ChatIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000, examples=["Tell me about GreatAPI"])


@app.get("/", include_in_schema=False)
async def index() -> Response:
    """The browser UI."""
    return FileResponse(f"{HERE}/index.html")


@app.post("/chat", tags=["Chat"])
async def chat(request: Request, body: ChatIn, session: DbSession) -> Response:
    """Stream a model's reply token by token.

    `sse` handles the framing, the heartbeat, and cancelling the model call if
    the browser goes away -- so an abandoned tab stops costing money.
    """
    record = Conversation(prompt=body.prompt, model=get_settings().ai_default_model)
    session.add(record)
    await session.commit()

    return ai.sse(ai.stream(messages=body.prompt), request=request)


@app.post("/agent", tags=["Chat"])
async def run_agent(request: Request, body: ChatIn) -> Response:
    """Run the tool-calling agent, streaming every step.

    The browser sees `text`, `tool_call` and `step` events as they happen, and
    the whole run is recorded as a trace under /admin/usage.
    """
    return ai.sse(support_agent.stream(body.prompt), request=request)


@app.post("/summarise/{conversation_id}", tags=["Jobs"])
async def summarise(conversation_id: int) -> dict[str, object]:
    """Queue slow work and return immediately. Poll `GET /jobs/{id}`."""
    queued = await enqueue(summarise_conversation, conversation_id=conversation_id)
    return {"job_id": queued.id, "poll": f"/jobs/{queued.id}"}


@app.post("/metered", tags=["Chat"])
async def metered(
    request: Request,
    body: ChatIn,
    key: object = Depends(ai.require_api_key("chat:write")),
) -> Response:
    """The same endpoint, behind an API key with a scope, rate limit and budget.

    Create a key at /admin/api-keys, then:

        curl -N localhost:8000/metered -H 'X-API-Key: gapi_...' \\
             -H 'content-type: application/json' -d '{"prompt": "hi"}'
    """
    return ai.sse(ai.stream(messages=body.prompt), request=request)
