"""The AI package, exercised entirely against the offline echo provider."""

from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import Response

from greatapi import GreatAPI, ai
from greatapi.ai.pricing import ModelPrice, estimate_cost, get_pricing, register_pricing
from greatapi.ai.providers import available_providers, reset_providers, resolve
from greatapi.ai.types import Message, Usage, normalise_messages
from greatapi.db.models import AgentRun, LLMCall, RunStatus
from greatapi.exceptions import GreatAPIError, MissingDependencyError


class TestModelResolution:
    def test_a_qualified_model_resolves(self) -> None:
        provider, model = resolve("echo:demo")
        assert provider.name == "echo"
        assert model == "demo"

    def test_a_missing_prefix_explains_itself(self) -> None:
        with pytest.raises(GreatAPIError, match="missing its provider prefix"):
            resolve("claude-sonnet-5")

    def test_an_unknown_provider_lists_the_known_ones(self) -> None:
        with pytest.raises(GreatAPIError, match="Unknown provider"):
            resolve("nosuchvendor:model")

    def test_the_builtin_providers_are_registered(self) -> None:
        assert set(available_providers()) >= {"echo", "anthropic", "openai", "local"}

    def test_a_custom_provider_can_be_registered(self) -> None:
        from greatapi.ai.providers import register_provider
        from greatapi.ai.providers.echo import EchoProvider

        register_provider("house", EchoProvider)
        try:
            provider, model = resolve("house:whatever")
            assert provider.name == "echo"
            assert model == "whatever"
        finally:
            reset_providers()


class TestOptionalDependencies:
    def test_a_missing_sdk_names_the_extra_to_install(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole point of shipping the AI code in the base wheel."""
        import importlib

        real = importlib.import_module

        def fake(name: str, package: str | None = None) -> object:
            if name == "anthropic":
                raise ImportError("No module named 'anthropic'")
            return real(name, package)

        monkeypatch.setattr(importlib, "import_module", fake)
        reset_providers()

        with pytest.raises(MissingDependencyError) as caught:
            resolve("anthropic:claude-sonnet-5")

        message = str(caught.value)
        assert 'pip install "greatapi[anthropic]"' in message
        assert "anthropic" in message
        reset_providers()

    def test_the_ai_module_imports_without_any_extra(self) -> None:
        import greatapi.ai

        assert greatapi.ai.complete is not None


class TestMessages:
    def test_a_bare_string_becomes_a_user_turn(self) -> None:
        assert normalise_messages("hi") == [Message(role="user", content="hi")]

    def test_dicts_are_accepted(self) -> None:
        result = normalise_messages([{"role": "system", "content": "be terse"}])
        assert result[0].role == "system"

    def test_multimodal_blocks_keep_their_text(self) -> None:
        result = normalise_messages(
            [{"role": "user", "content": [{"type": "text", "text": "look"}]}]
        )
        assert result[0].content == "look"

    def test_usage_adds_up(self) -> None:
        total = Usage(prompt_tokens=1, completion_tokens=2) + Usage(
            prompt_tokens=3, completion_tokens=4
        )
        assert (total.prompt_tokens, total.completion_tokens, total.total_tokens) == (4, 6, 10)


class TestComplete:
    async def test_a_completion_reports_tokens_cost_and_latency(
        self, session: AsyncSession
    ) -> None:
        result = await ai.complete("echo:demo", "Say hello")
        assert "Say hello" in result.text
        assert result.provider == "echo"
        assert result.usage.total_tokens > 0
        assert result.cost_usd > 0
        assert result.latency_ms >= 0

    async def test_the_call_is_recorded(self, session: AsyncSession) -> None:
        await ai.complete("echo:demo", "record me")

        record = (await session.execute(select(LLMCall))).scalars().one()
        assert record.model == "echo:demo"
        assert record.operation == "complete"
        assert record.status is RunStatus.succeeded
        assert record.total_tokens > 0

    async def test_a_transient_failure_is_retried_then_surfaces(
        self, session: AsyncSession
    ) -> None:
        with pytest.raises(ai.ProviderError, match="rate limit"):
            await ai.complete("echo:demo", "__transient__", max_retries=2)

        record = (await session.execute(select(LLMCall))).scalars().one()
        assert record.status is RunStatus.failed, "failures are recorded too"
        assert "rate limit" in (record.error or "")

    async def test_a_permanent_failure_is_not_retried(self, session: AsyncSession) -> None:
        with pytest.raises(ai.ProviderError):
            await ai.complete("echo:demo", "__fail__", max_retries=3)

        # One recorded attempt: a 400 must not be retried three times.
        assert await session.scalar(select(func.count()).select_from(LLMCall)) == 1


class TestStream:
    async def test_chunks_arrive_and_usage_is_recorded(self, session: AsyncSession) -> None:
        chunks = [chunk async for chunk in ai.stream("echo:demo", "stream me")]

        assert chunks, "should yield something"
        assert all(chunk.type == "text" for chunk in chunks)
        assert "stream me" in "".join(chunk.text for chunk in chunks)

        record = (await session.execute(select(LLMCall))).scalars().one()
        assert record.operation == "stream"
        assert record.total_tokens > 0

    async def test_usage_chunks_are_absorbed_not_forwarded(self, session: AsyncSession) -> None:
        # A usage frame is bookkeeping; it should not reach the browser as text.
        chunks = [chunk async for chunk in ai.stream("echo:demo", "hello")]
        assert not any(chunk.type == "usage" for chunk in chunks)


class TestPricing:
    def test_echo_is_priced_so_the_demo_shows_cost(self) -> None:
        assert get_pricing("echo:demo") is not None

    def test_an_unknown_model_costs_zero_rather_than_guessing(self) -> None:
        usage = Usage(prompt_tokens=1000, completion_tokens=1000)
        assert estimate_cost("mystery:model", usage) == 0.0

    def test_registering_a_price_activates_cost(self) -> None:
        register_pricing("vendor:model", input_per_1m=3.0, output_per_1m=15.0)
        cost = estimate_cost("vendor:model", Usage(prompt_tokens=1_000_000, completion_tokens=0))
        assert cost == pytest.approx(3.0)

    def test_the_bare_model_name_also_matches(self) -> None:
        register_pricing("some-model", input_per_1m=1.0, output_per_1m=1.0)
        assert get_pricing("vendor:some-model") is not None

    def test_cost_uses_input_and_output_rates_separately(self) -> None:
        price = ModelPrice(input_per_1m=1.0, output_per_1m=10.0)
        cost = price.cost(Usage(prompt_tokens=1_000_000, completion_tokens=1_000_000))
        assert cost == pytest.approx(11.0)


class TestTools:
    def test_a_schema_is_derived_from_type_hints(self) -> None:
        @ai.tool
        async def lookup_order(order_id: int, include_history: bool = False) -> dict[str, str]:
            """Fetch an order by its id."""
            return {}

        assert lookup_order.name == "lookup_order"
        assert lookup_order.description == "Fetch an order by its id."

        properties = lookup_order.parameters["properties"]
        assert properties["order_id"] == {"type": "integer"}
        assert properties["include_history"] == {"type": "boolean"}
        # Only the parameter without a default is required.
        assert lookup_order.parameters["required"] == ["order_id"]

    def test_a_tool_can_be_named_explicitly(self) -> None:
        @ai.tool("search", description="Search the catalogue.")
        async def _search(query: str) -> str:
            return query

        assert _search.name == "search"
        assert _search.description == "Search the catalogue."

    async def test_a_sync_tool_is_supported(self) -> None:
        @ai.tool
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        assert await add.invoke({"a": 2, "b": 3}) == 5


class TestAgent:
    async def test_it_calls_a_tool_then_answers(self, session: AsyncSession) -> None:
        calls: list[int] = []

        @ai.tool
        async def lookup_order(order_id: int) -> dict[str, object]:
            """Fetch an order."""
            calls.append(order_id)
            return {"status": "shipped"}

        agent = ai.Agent(model="echo:demo", tools=[lookup_order], name="support", max_steps=4)
        result = await agent.run("__tool__ where is my order")

        assert calls, "the tool should have run"
        assert result.steps == 2, "call the tool, then answer"
        assert result.usage.total_tokens > 0

    async def test_the_run_is_persisted_as_a_trace(self, session: AsyncSession) -> None:
        @ai.tool
        async def noop() -> str:
            """Do nothing."""
            return "done"

        agent = ai.Agent(model="echo:demo", tools=[noop], name="tracer")
        result = await agent.run("__tool__ go")

        run = await session.get(AgentRun, result.run_id)
        assert run is not None
        assert run.status is RunStatus.succeeded
        assert run.steps == result.steps
        assert run.total_tokens > 0

        linked = await session.scalar(
            select(func.count()).select_from(LLMCall).where(LLMCall.agent_run_id == run.id)
        )
        assert linked == result.steps, "every step is linked to the run"

    async def test_a_failing_tool_is_reported_to_the_model_not_raised(
        self, session: AsyncSession
    ) -> None:
        @ai.tool
        async def explode() -> str:
            """Always fails."""
            raise RuntimeError("boom")

        agent = ai.Agent(model="echo:demo", tools=[explode], max_steps=3)
        result = await agent.run("__tool__ try it")

        tool_output = [m for m in result.messages if m.role == "tool"]
        assert tool_output and "boom" in tool_output[0].content

    async def test_max_steps_is_a_hard_ceiling(self, session: AsyncSession) -> None:
        """A model that keeps asking for tools must not spend forever."""

        @ai.tool
        async def always() -> str:
            """Returns a marker that keeps the echo provider asking again."""
            return "__tool__ again"

        agent = ai.Agent(model="echo:demo", tools=[always], max_steps=2, name="bounded")
        result = await agent.run("__tool__ start")
        assert result.steps <= 2

    def test_max_steps_must_be_positive(self) -> None:
        with pytest.raises(GreatAPIError, match="max_steps"):
            ai.Agent(model="echo:demo", max_steps=0)

    async def test_streaming_emits_typed_events(self, session: AsyncSession) -> None:
        @ai.tool
        async def lookup() -> str:
            """Look something up."""
            return "found"

        agent = ai.Agent(model="echo:demo", tools=[lookup], max_steps=3)
        kinds = [chunk.type async for chunk in agent.stream("__tool__ go")]

        assert "tool_call" in kinds
        assert "text" in kinds
        assert kinds[-1] == "step", "the final event carries the result"


class TestOverHttp:
    async def test_a_streaming_chat_endpoint(self, engine: object) -> None:
        app = GreatAPI(title="chat", admin=False, jobs=False, create_tables=False)

        @app.post("/chat")
        async def chat(request: Request) -> Response:
            return ai.sse(ai.stream("echo:demo", "hello world"), request=request)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/chat")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "event: done" in response.text

        # Chunks arrive as JSON named by chunk type, not as a repr().
        assert "event: text" in response.text
        assert "Chunk(" not in response.text, "chunks must be serialised, not repr'd"

        payloads = [
            json.loads(line[len("data: ") :])
            for line in response.text.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"
        ]
        assert all(item["type"] == "text" for item in payloads)
        assert "hello world" in "".join(item.get("text", "") for item in payloads)
