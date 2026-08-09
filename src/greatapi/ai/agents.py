"""A tool-calling agent loop.

The loop itself is fifteen lines; what takes the work is everything around it,
and that is what this module provides:

* JSON Schemas derived from your function's type hints, so a tool is a normal
  Python function and not a hand-written schema that drifts from it
* a hard step ceiling, because a model that keeps calling tools will otherwise
  keep spending money until something else stops it
* every step streamed as a typed event, so a UI can show the work
* every step persisted, so a finished run is a trace you can open in the admin
  rather than a number in a log line
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar, get_type_hints

from pydantic import TypeAdapter

from greatapi.ai.client import complete
from greatapi.ai.types import Chunk, Message, ToolCall, ToolSpec, Usage, normalise_messages
from greatapi.db.base import utcnow
from greatapi.db.models import AgentRun, RunStatus
from greatapi.db.session import session_scope
from greatapi.exceptions import GreatAPIError

__all__ = ["Agent", "AgentResult", "Tool", "tool"]

logger = logging.getLogger("greatapi.ai.agents")

F = TypeVar("F", bound=Callable[..., Any])

_JSON_TYPES: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


@dataclass(slots=True)
class Tool:
    """A Python function the model may call."""

    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., Any]

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, parameters=self.parameters)

    async def invoke(self, arguments: dict[str, Any]) -> Any:
        result = self.func(**arguments)
        if inspect.isawaitable(result):
            return await result
        return result


def tool(name_or_func: str | Callable[..., Any] | None = None, *, description: str = "") -> Any:
    """Turn a function into a tool the model can call.

    The schema comes from the signature and the docstring, so there is one
    source of truth::

        @ai.tool
        async def lookup_order(order_id: int) -> dict:
            \"\"\"Fetch an order by its id.\"\"\"
            ...
    """

    def build(func: Callable[..., Any], explicit_name: str | None) -> Tool:
        doc = inspect.getdoc(func) or ""
        return Tool(
            name=explicit_name or func.__name__,
            description=description or doc.split("\n\n")[0] or func.__name__,
            parameters=schema_for(func),
            func=func,
        )

    if callable(name_or_func):
        return build(name_or_func, None)

    def decorator(func: Callable[..., Any]) -> Tool:
        return build(func, name_or_func)

    return decorator


def schema_for(func: Callable[..., Any]) -> dict[str, Any]:
    """Build a JSON Schema for a function's parameters from its annotations."""
    signature = inspect.signature(func)
    try:
        hints = get_type_hints(func)
    except Exception:  # pragma: no cover - unresolvable forward refs
        hints = {}

    properties: dict[str, Any] = {}
    required: list[str] = []

    for parameter in signature.parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        annotation = hints.get(parameter.name, str)
        properties[parameter.name] = _json_schema(annotation)
        if parameter.default is inspect.Parameter.empty:
            required.append(parameter.name)

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _json_schema(annotation: Any) -> dict[str, Any]:
    if annotation in _JSON_TYPES:
        return {"type": _JSON_TYPES[annotation]}
    try:
        # Pydantic understands unions, enums, dataclasses and models; fall back
        # to a plain string for anything it cannot describe.
        generated = TypeAdapter(annotation).json_schema()
    except Exception:
        return {"type": "string"}
    generated.pop("title", None)
    return generated


@dataclass(slots=True)
class AgentResult:
    """The outcome of a finished run."""

    output: str
    steps: int
    usage: Usage
    cost_usd: float
    messages: list[Message] = field(default_factory=list)
    run_id: int | None = None


class Agent:
    """A model plus tools, run to completion or to a step ceiling.

    ::

        agent = ai.Agent(
            model="anthropic:claude-sonnet-5",
            tools=[lookup_order],
            system="You are a support assistant.",
            max_steps=8,
        )

        result = await agent.run("Where is order 4021?")
        # or, streamed to a browser:
        return sse(agent.stream("Where is order 4021?"), request=request)
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        tools: list[Tool | Callable[..., Any]] | None = None,
        system: str | None = None,
        name: str = "agent",
        max_steps: int = 8,
        temperature: float | None = None,
        max_tokens: int | None = None,
        track: bool = True,
    ) -> None:
        if max_steps < 1:
            raise GreatAPIError("max_steps must be at least 1.")
        self.model = model
        self.system = system
        self.name = name
        self.max_steps = max_steps
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.track = track
        self.tools: dict[str, Tool] = {}
        for entry in tools or []:
            resolved = entry if isinstance(entry, Tool) else tool(entry)
            self.tools[resolved.name] = resolved

    @property
    def specs(self) -> list[ToolSpec]:
        return [item.spec for item in self.tools.values()]

    # -- running ----------------------------------------------------------

    async def run(
        self, prompt: str | Message | list[Message] | list[dict[str, Any]]
    ) -> AgentResult:
        """Run to completion and return the final answer."""
        result: AgentResult | None = None
        async for chunk in self.stream(prompt):
            if chunk.type == "step" and chunk.detail.get("event") == "finished":
                result = chunk.detail["result"]
        if result is None:  # pragma: no cover - stream always emits a finish
            raise GreatAPIError("Agent finished without producing a result.")
        return result

    async def stream(
        self, prompt: str | Message | list[Message] | list[dict[str, Any]]
    ) -> AsyncIterator[Chunk]:
        """Run the agent, yielding a typed event for every step.

        Emits ``text`` as the answer forms, ``tool_call`` when the model asks for
        a tool, ``step`` with the tool's result, and a final ``step`` carrying the
        :class:`AgentResult`.
        """
        conversation = normalise_messages(prompt)
        prompt_text = "\n".join(m.content for m in conversation if m.role == "user")

        run = await self._start_run(prompt_text) if self.track else None
        run_id = run.id if run is not None else None

        started = time.perf_counter()
        total = Usage()
        cost = 0.0
        steps = 0
        answer = ""
        failure: str | None = None

        try:
            for step in range(self.max_steps):
                steps = step + 1
                result = await complete(
                    self.model,
                    conversation,
                    tools=self.specs or None,
                    system=self.system,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    agent_run_id=run_id,
                )
                total = total + result.usage
                cost += result.cost_usd

                if result.text:
                    yield Chunk(type="text", text=result.text)

                if not result.tool_calls:
                    answer = result.text
                    conversation.append(result.as_message())
                    break

                conversation.append(result.as_message())
                for call in result.tool_calls:
                    yield Chunk(type="tool_call", tool_call=call)
                    output = await self._invoke(call)
                    yield Chunk(
                        type="step",
                        detail={"event": "tool_result", "tool": call.name, "output": output},
                    )
                    conversation.append(
                        Message(role="tool", content=output, tool_call_id=call.id, name=call.name)
                    )
            else:
                # Ran out of steps with the model still wanting tools.
                failure = f"Agent stopped after reaching max_steps={self.max_steps}."
                logger.warning("%s (%s)", failure, self.name)

            yield Chunk(type="usage", usage=total)
            outcome = AgentResult(
                output=answer,
                steps=steps,
                usage=total,
                cost_usd=cost,
                messages=conversation,
                run_id=run_id,
            )
            yield Chunk(type="step", detail={"event": "finished", "result": outcome})

        except asyncio.CancelledError:
            failure = failure or "Cancelled."
            raise
        except Exception as exc:
            failure = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            if run_id is not None:
                await self._finish_run(
                    run_id,
                    output=answer,
                    steps=steps,
                    usage=total,
                    cost=cost,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error=failure,
                )

    # -- tool execution ---------------------------------------------------

    async def _invoke(self, call: ToolCall) -> str:
        """Run one tool. Failures come back to the model as text, not exceptions.

        A tool raising should let the model recover -- retry with different
        arguments, or explain the problem -- rather than tearing down the run.
        """
        target = self.tools.get(call.name)
        if target is None:
            return f"Error: no tool named {call.name!r}. Available: {', '.join(self.tools)}."
        try:
            value = await target.invoke(call.arguments)
        except Exception as exc:
            logger.warning("Tool %s failed", call.name, exc_info=True)
            return f"Error running {call.name}: {type(exc).__name__}: {exc}"
        return _to_text(value)

    # -- persistence ------------------------------------------------------

    async def _start_run(self, prompt: str) -> AgentRun | None:
        record = AgentRun(
            name=self.name,
            model=self.model or "",
            status=RunStatus.running,
            prompt=prompt[:4000],
        )
        try:
            async with session_scope() as session:
                session.add(record)
                await session.flush()
                await session.refresh(record)
        except Exception:
            logger.warning("Could not start an agent run record", exc_info=True)
            return None
        return record

    async def _finish_run(
        self,
        run_id: int,
        *,
        output: str,
        steps: int,
        usage: Usage,
        cost: float,
        latency_ms: int,
        error: str | None,
    ) -> None:
        try:
            async with session_scope() as session:
                record = await session.get(AgentRun, run_id)
                if record is None:
                    return
                record.status = RunStatus.failed if error else RunStatus.succeeded
                record.output = output[:8000] if output else None
                record.error = error
                record.steps = steps
                record.total_tokens = usage.total_tokens
                record.cost_usd = cost
                record.latency_ms = latency_ms
                record.updated_at = utcnow()
        except Exception:
            logger.warning("Could not finalise agent run %s", run_id, exc_info=True)


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except Exception:
        return str(value)
