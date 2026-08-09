"""The application class: lifespan, wiring and opt-outs; plus CLI command bodies."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from greatapi import GreatAPI
from greatapi.cli import app as cli_app
from greatapi.db.models import Job, JobStatus
from greatapi.jobs import enqueue, job

runner = CliRunner()


class TestWiring:
    def test_the_admin_is_mounted_by_default(self, engine: Any) -> None:
        app = GreatAPI(title="wired", jobs=False, create_tables=False)
        assert app.enable_admin is True
        assert any(getattr(r, "path", "") == "/admin/_static" for r in app.routes)

    def test_the_admin_can_be_turned_off(self, engine: Any) -> None:
        app = GreatAPI(title="bare", admin=False, jobs=False, create_tables=False)
        assert app.enable_admin is False
        assert not any("_static" in getattr(r, "path", "") for r in app.routes)

    async def test_admin_off_means_no_admin_routes(self, engine: Any) -> None:
        app = GreatAPI(title="bare", admin=False, jobs=False, create_tables=False)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            assert (await client.get("/admin")).status_code == 404

    async def test_the_jobs_endpoint_is_always_present(self, engine: Any) -> None:
        app = GreatAPI(title="jobs", admin=False, jobs=False, create_tables=False)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            assert (await client.get("/jobs/1")).status_code == 404  # routed, just no such job

    def test_a_title_defaults_to_the_configured_one(self, engine: Any) -> None:
        app = GreatAPI(jobs=False, create_tables=False)
        assert app.title == app.settings.admin_title


class TestSecurityHeaders:
    async def test_they_are_added_to_every_response(self, engine: Any) -> None:
        app = GreatAPI(title="hdr", admin=False, jobs=False, create_tables=False)

        @app.get("/anything")
        async def anything() -> dict[str, bool]:
            return {"ok": True}

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            response = await client.get("/anything")

        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        # The strict CSP is admin-only; an API response should not carry it.
        assert "content-security-policy" not in response.headers


class TestLifespan:
    async def test_it_creates_tables_and_starts_the_worker(self, tmp_path: Path) -> None:
        from greatapi.db.session import configure_engine, dispose_engine

        configure_engine(f"sqlite+aiosqlite:///{tmp_path / 'life.db'}")
        ran = asyncio.Event()

        @job("lifespan-job")
        async def handler() -> str:
            ran.set()
            return "done"

        app = GreatAPI(title="life", admin=False, jobs=True, create_tables=True)

        async with app.router.lifespan_context(app):
            assert app.worker is not None, "the worker should be running"
            await enqueue(handler)
            await asyncio.wait_for(ran.wait(), timeout=5.0)

        # Shutdown stops the worker and releases the pool.
        assert app.worker is None
        await dispose_engine()

    async def test_a_user_lifespan_still_runs(self, engine: Any) -> None:
        from contextlib import asynccontextmanager

        events: list[str] = []

        @asynccontextmanager
        async def user_lifespan(_app: Any) -> Any:
            events.append("start")
            yield
            events.append("stop")

        app = GreatAPI(
            title="chained",
            admin=False,
            jobs=False,
            create_tables=False,
            lifespan=user_lifespan,
        )
        async with app.router.lifespan_context(app):
            assert events == ["start"]
        assert events == ["start", "stop"]

    async def test_an_interrupted_job_is_requeued_on_shutdown(self, tmp_path: Path) -> None:
        """A job cut short by shutdown must not be left stuck in `running`."""
        from greatapi.db.session import configure_engine, dispose_engine, session_scope
        from greatapi.jobs.worker import run_job

        configure_engine(f"sqlite+aiosqlite:///{tmp_path / 'interrupt.db'}")
        from greatapi.db.base import Base
        from greatapi.db.session import get_engine

        async with get_engine().begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        started = asyncio.Event()

        @job("long-running")
        async def handler() -> None:
            started.set()
            await asyncio.sleep(30)

        record = await enqueue(handler)

        from greatapi.jobs.queue import claim_jobs

        async with session_scope() as session:
            claimed = await claim_jobs(session, 1)

        task = asyncio.create_task(run_job(claimed[0]))
        await asyncio.wait_for(started.wait(), timeout=5.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        async with session_scope() as session:
            refreshed = await session.get(Job, record.id)
            assert refreshed is not None
            assert refreshed.status is JobStatus.queued, "must go back on the queue"

        await dispose_engine()


class TestCliCommands:
    def test_runserver_passes_its_options_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import uvicorn

        captured: dict[str, Any] = {}
        monkeypatch.setattr(uvicorn, "run", lambda app, **kw: captured.update(app=app, **kw))

        result = runner.invoke(
            cli_app,
            ["runserver", "--host", "0.0.0.0", "--port", "9001", "--no-reload"],  # noqa: S104
        )
        assert result.exit_code == 0
        assert captured["app"] == "main:app"
        assert captured["host"] == "0.0.0.0"  # noqa: S104
        assert captured["port"] == 9001
        assert captured["reload"] is False

    def test_reload_is_disabled_for_multiple_workers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import uvicorn

        captured: dict[str, Any] = {}
        monkeypatch.setattr(uvicorn, "run", lambda app, **kw: captured.update(app=app, **kw))

        result = runner.invoke(cli_app, ["runserver", "--workers", "4"])
        assert result.exit_code == 0
        assert captured["reload"] is False
        assert "Reload is off" in result.output

    def test_createsuperuser_requires_everything_with_noinput(self) -> None:
        result = runner.invoke(cli_app, ["createsuperuser", "--noinput", "--email", "a@b.c"])
        assert result.exit_code == 1
        assert "--noinput needs" in result.output

    def test_createsuperuser_reports_a_weak_password(self, tmp_path: Path) -> None:
        from greatapi.db.session import configure_engine

        configure_engine(f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}")
        result = runner.invoke(
            cli_app,
            [
                "createsuperuser",
                "--noinput",
                "--email",
                "weak@example.com",
                "--username",
                "weak",
                "--password",
                "short",
            ],
        )
        assert result.exit_code == 1
        assert "at least" in result.output

    def test_createsuperuser_creates_an_account(self, tmp_path: Path) -> None:
        from greatapi.db.session import configure_engine

        configure_engine(f"sqlite+aiosqlite:///{tmp_path / 'cli2.db'}")
        result = runner.invoke(
            cli_app,
            [
                "createsuperuser",
                "--noinput",
                "--email",
                "boss@example.com",
                "--username",
                "boss",
                "--password",
                "hunter2hunter2",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Created superuser" in result.output

    def test_the_help_lists_every_command(self) -> None:
        result = runner.invoke(cli_app, ["--help"])
        assert result.exit_code == 0
        for command in [
            "startproject",
            "startapp",
            "runserver",
            "createsuperuser",
            "makemigrations",
            "migrate",
            "downgrade",
            "routes",
        ]:
            assert command in result.output

    @pytest.mark.parametrize("command", ["makemigrations", "downgrade", "history"])
    def test_database_commands_explain_a_missing_project(self, command: str) -> None:
        result = runner.invoke(cli_app, [command])
        assert result.exit_code == 1
        assert "migrations" in result.output.lower()
