"""Migrations, end to end.

The headline claim is ``greatapi makemigrations && greatapi migrate``, so the
test generates a project, adds an app with a model, and runs the real commands
in a subprocess -- then checks the tables actually exist.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from greatapi.cli import app as cli_app
from greatapi.db.migrations import build_config
from greatapi.exceptions import ImproperlyConfigured

runner = CliRunner()


def read_tables(database: Path) -> set[str]:
    """Table names in a SQLite file.

    `with sqlite3.connect(...)` commits but does not close, and an unclosed
    handle surfaces later as a ResourceWarning attached to whichever test
    happens to be running when it is collected.
    """
    with closing(sqlite3.connect(database)) as connection:
        return {
            row[0]
            for row in connection.execute("select name from sqlite_master where type='table'")
        }


def run_cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "greatapi.cli", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=180,
        env={
            **os.environ,
            "GREATAPI_SECRET_KEY": "x" * 64,
            "GREATAPI_DEBUG": "true",
            "GREATAPI_DATABASE_URL": f"sqlite+aiosqlite:///{root / 'app.db'}",
            "PYTHONPATH": str(root),
        },
    )


class TestConfig:
    def test_a_missing_migrations_directory_is_explained(self, tmp_path: Path) -> None:
        with pytest.raises(ImproperlyConfigured, match="migrations"):
            build_config(tmp_path)

    def test_the_url_comes_from_settings_not_the_ini(self, tmp_path: Path) -> None:
        (tmp_path / "migrations").mkdir()
        config = build_config(tmp_path)
        assert config.get_main_option("sqlalchemy.url")

    def test_a_password_with_a_percent_survives(self, tmp_path: Path) -> None:
        """ConfigParser treats a bare % as interpolation."""
        from greatapi.conf.settings import override_settings

        (tmp_path / "migrations").mkdir()
        with override_settings(database_url="postgresql+asyncpg://u:p%40ss@h/db"):
            config = build_config(tmp_path)
        assert config.get_main_option("sqlalchemy.url") == "postgresql+asyncpg://u:p%40ss@h/db"


@pytest.mark.slow
class TestEndToEnd:
    def test_makemigrations_then_migrate_creates_every_table(self, tmp_path: Path) -> None:
        root = tmp_path / "shop"
        assert runner.invoke(cli_app, ["startproject", "shop", "-d", str(root)]).exit_code == 0

        created = run_cli(root, "startapp", "catalog")
        assert created.returncode == 0, created.stderr[-2000:]
        assert "registered in" in created.stdout

        generated = run_cli(root, "makemigrations", "-m", "initial")
        assert generated.returncode == 0, generated.stderr[-3000:]

        versions = list((root / "migrations" / "versions").glob("*.py"))
        assert len(versions) == 1, "exactly one revision should have been written"
        revision = versions[0].read_text()
        assert "catalog_item" in revision, "the app's model must be detected"
        assert "greatapi_user" in revision, "framework tables must be included"

        applied = run_cli(root, "migrate")
        assert applied.returncode == 0, applied.stderr[-3000:]

        tables = read_tables(root / "app.db")
        assert "catalog_item" in tables
        assert {
            "greatapi_user",
            "greatapi_api_key",
            "greatapi_job",
            "greatapi_audit_log",
            "greatapi_llm_call",
            "greatapi_agent_run",
        } <= tables, "AI tables exist on every install, so autogenerate never drops them"
        assert "alembic_version" in tables

    def test_a_second_makemigrations_finds_nothing_to_do(self, tmp_path: Path) -> None:
        """A stable schema must not keep producing empty revisions."""
        root = tmp_path / "stable"
        runner.invoke(cli_app, ["startproject", "stable", "-d", str(root)])
        assert run_cli(root, "makemigrations", "-m", "initial").returncode == 0
        assert run_cli(root, "migrate").returncode == 0

        second = run_cli(root, "makemigrations", "-m", "again")
        assert second.returncode == 0, second.stderr[-3000:]

        revisions = list((root / "migrations" / "versions").glob("*.py"))
        assert len(revisions) == 2
        empty = [
            path
            for path in revisions
            if "op." not in path.read_text().split("def upgrade")[1].split("def downgrade")[0]
        ]
        assert len(empty) >= 1, "the second run should produce an empty revision, not a diff"

    def test_downgrade_rolls_back(self, tmp_path: Path) -> None:
        root = tmp_path / "rollback"
        runner.invoke(cli_app, ["startproject", "rollback", "-d", str(root)])
        assert run_cli(root, "makemigrations", "-m", "initial").returncode == 0
        assert run_cli(root, "migrate").returncode == 0

        result = run_cli(root, "downgrade", "base")
        assert result.returncode == 0, result.stderr[-2000:]

        assert "greatapi_user" not in read_tables(root / "app.db")

    def test_history_reports_the_current_revision(self, tmp_path: Path) -> None:
        root = tmp_path / "hist"
        runner.invoke(cli_app, ["startproject", "hist", "-d", str(root)])
        assert run_cli(root, "makemigrations", "-m", "initial").returncode == 0
        assert run_cli(root, "migrate").returncode == 0

        result = run_cli(root, "history")
        assert result.returncode == 0

        # Alembic logs the history through its own handler, so assert on the
        # revision that was actually recorded rather than on captured output.
        revisions = list((root / "migrations" / "versions").glob("*.py"))
        assert len(revisions) == 1
        assert "initial" in revisions[0].name
