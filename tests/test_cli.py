"""The CLI, scaffolding and configuration.

The scaffolding tests generate a project on disk and then *import* it, because
"the files were written" is not the same claim as "the project runs".
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from greatapi import __version__
from greatapi.cli import app as cli_app
from greatapi.cli.scaffold import (
    APP_TEMPLATE_DIR,
    PROJECT_TEMPLATE_DIR,
    generate_secret_key,
    register_app,
    render_tree,
    validate_name,
)
from greatapi.exceptions import GreatAPIError, ImproperlyConfigured

runner = CliRunner()


class TestNameValidation:
    @pytest.mark.parametrize("name", ["blog", "my_app", "_private", "App2"])
    def test_valid_names(self, name: str) -> None:
        assert validate_name(name) == name

    @pytest.mark.parametrize(
        "name",
        ["", "2fast", "my-app", "my app", "my/app", "my.app", "../escape"],
    )
    def test_malformed_names_are_refused(self, name: str) -> None:
        with pytest.raises(GreatAPIError):
            validate_name(name)

    @pytest.mark.parametrize("name", ["class", "import", "None", "lambda"])
    def test_keywords_are_refused(self, name: str) -> None:
        with pytest.raises(GreatAPIError, match="keyword"):
            validate_name(name)

    @pytest.mark.parametrize("name", ["greatapi", "fastapi", "migrations", "main", "admin"])
    def test_shadowing_names_are_refused(self, name: str) -> None:
        with pytest.raises(GreatAPIError, match="shadow"):
            validate_name(name)


class TestSecretGeneration:
    def test_a_key_is_long_and_unique(self) -> None:
        first, second = generate_secret_key(), generate_secret_key()
        assert len(first) >= 64
        assert first != second

    def test_the_command_prints_one(self) -> None:
        result = runner.invoke(cli_app, ["generate-secret"])
        assert result.exit_code == 0
        assert len(result.stdout.strip()) >= 64


class TestVersion:
    def test_version_flag(self) -> None:
        result = runner.invoke(cli_app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.stdout


class TestStartProject:
    def test_it_produces_a_complete_tree(self, tmp_path: Path) -> None:
        result = runner.invoke(cli_app, ["startproject", "shop", "-d", str(tmp_path / "shop")])
        assert result.exit_code == 0, result.output

        root = tmp_path / "shop"
        for expected in [
            "main.py",
            "README.md",
            ".env.example",
            ".gitignore",
            "alembic.ini",
            "shop/__init__.py",
            "shop/settings.py",
            "migrations/env.py",
            "migrations/script.py.mako",
        ]:
            assert (root / expected).exists(), f"missing {expected}"

        # No template artefacts should survive into the generated project.
        assert not list(root.rglob("*-tpl"))
        assert not list(root.rglob("*.py-tpl"))

    def test_the_generated_env_has_a_real_secret(self, tmp_path: Path) -> None:
        runner.invoke(cli_app, ["startproject", "shop", "-d", str(tmp_path / "shop")])
        env = (tmp_path / "shop" / ".env.example").read_text()

        line = next(row for row in env.splitlines() if row.startswith("GREATAPI_SECRET_KEY="))
        secret = line.split("=", 1)[1]
        assert len(secret) >= 64
        assert "{{" not in env, "the template was not rendered"

    def test_two_projects_get_different_secrets(self, tmp_path: Path) -> None:
        secrets = []
        for name in ("one", "two"):
            runner.invoke(cli_app, ["startproject", name, "-d", str(tmp_path / name)])
            secrets.append((tmp_path / name / ".env.example").read_text())
        assert secrets[0] != secrets[1]

    def test_the_generated_code_is_valid_python(self, tmp_path: Path) -> None:
        runner.invoke(cli_app, ["startproject", "shop", "-d", str(tmp_path / "shop")])
        for path in (tmp_path / "shop").rglob("*.py"):
            compile(path.read_text(), str(path), "exec")

    def test_an_existing_directory_is_refused(self, tmp_path: Path) -> None:
        target = tmp_path / "taken"
        target.mkdir()
        (target / "something").write_text("hi")

        result = runner.invoke(cli_app, ["startproject", "taken", "-d", str(target)])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_a_bad_name_is_refused_clearly(self, tmp_path: Path) -> None:
        result = runner.invoke(cli_app, ["startproject", "my-app", "-d", str(tmp_path / "x")])
        assert result.exit_code == 1
        assert "not a valid" in result.output


class TestStartApp:
    def test_it_registers_itself_in_installed_apps(self, tmp_path: Path) -> None:
        settings = tmp_path / "proj" / "settings.py"
        settings.parent.mkdir(parents=True)
        settings.write_text("INSTALLED_APPS: list[str] = [\n]\n")

        render_tree(APP_TEMPLATE_DIR, tmp_path / "blog", {"app_name": "blog"})
        assert register_app(settings, "blog") is True

        updated = settings.read_text()
        assert '"blog",' in updated
        # And the result is still valid Python.
        compile(updated, "settings.py", "exec")

    def test_registering_twice_is_a_no_op(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.py"
        settings.write_text('INSTALLED_APPS: list[str] = [\n    "blog",\n]\n')
        assert register_app(settings, "blog") is False

    def test_a_missing_settings_file_is_handled(self, tmp_path: Path) -> None:
        assert register_app(tmp_path / "nope.py", "blog") is False

    def test_the_app_template_renders_valid_python(self, tmp_path: Path) -> None:
        written = render_tree(APP_TEMPLATE_DIR, tmp_path / "blog", {"app_name": "blog"})
        assert written
        for path in written:
            if path.suffix == ".py":
                compile(path.read_text(), str(path), "exec")

    def test_the_app_template_covers_a_vertical_slice(self, tmp_path: Path) -> None:
        render_tree(APP_TEMPLATE_DIR, tmp_path / "blog", {"app_name": "blog"})
        names = {p.name for p in (tmp_path / "blog").iterdir()}
        assert names == {
            "__init__.py",
            "models.py",
            "schemas.py",
            "repository.py",
            "router.py",
            "admin.py",
        }


class TestGeneratedProjectRuns:
    """The claim that matters: the generated project imports and serves."""

    @pytest.mark.slow
    def test_a_generated_project_boots_and_answers(self, tmp_path: Path) -> None:
        runner.invoke(cli_app, ["startproject", "demo", "-d", str(tmp_path / "demo")])
        root = tmp_path / "demo"

        probe = root / "_probe.py"
        probe.write_text(
            "import asyncio\n"
            "import httpx\n"
            "from main import app\n"
            "\n"
            "async def go():\n"
            "    transport = httpx.ASGITransport(app=app)\n"
            "    async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:\n"
            "        async with app.router.lifespan_context(app):\n"
            "            health = await c.get('/health')\n"
            "            root_doc = await c.get('/')\n"
            "            admin = await c.get('/admin/login')\n"
            "    print('health', health.status_code, health.json())\n"
            "    print('root', root_doc.status_code)\n"
            "    print('admin', admin.status_code)\n"
            "\n"
            "asyncio.run(go())\n"
        )

        result = subprocess.run(  # noqa: S603
            [sys.executable, str(probe)],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
            env={
                **os.environ,
                "GREATAPI_SECRET_KEY": "x" * 64,
                "GREATAPI_DEBUG": "true",
                "GREATAPI_DATABASE_URL": f"sqlite+aiosqlite:///{root / 'demo.db'}",
                "PYTHONPATH": str(root),
            },
        )
        assert result.returncode == 0, result.stderr[-3000:]
        assert "health 200 {'status': 'ok'}" in result.stdout
        assert "root 200" in result.stdout
        assert "admin 200" in result.stdout, "the admin must be reachable out of the box"


class TestRoutesCommand:
    def test_it_explains_a_bad_target(self) -> None:
        result = runner.invoke(cli_app, ["routes", "--app", "not_a_module:app"])
        assert result.exit_code == 1
        assert "Could not import" in result.output

    def test_it_rejects_a_malformed_target(self) -> None:
        result = runner.invoke(cli_app, ["routes", "--app", "justamodule"])
        assert result.exit_code == 1
        assert "module:attribute" in result.output


class TestMigrateCommand:
    def test_it_explains_a_missing_migrations_directory(self, tmp_path: Path) -> None:
        result = runner.invoke(cli_app, ["migrate"], catch_exceptions=False)
        # Run from the repository root, which has no migrations/ of its own.
        assert result.exit_code == 1
        assert "migrations" in result.output.lower()


class TestSettings:
    def test_a_missing_secret_key_refuses_to_start(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from greatapi.conf.settings import Settings

        monkeypatch.delenv("GREATAPI_SECRET_KEY", raising=False)
        monkeypatch.setenv("GREATAPI_DEBUG", "false")

        with pytest.raises(ImproperlyConfigured, match="generate-secret"):
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_debug_generates_a_temporary_key_and_warns(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from greatapi.conf.settings import Settings

        monkeypatch.delenv("GREATAPI_SECRET_KEY", raising=False)
        monkeypatch.setenv("GREATAPI_DEBUG", "true")

        with pytest.warns(RuntimeWarning, match="temporary key"):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.secret_key is not None

    def test_secure_cookies_follow_debug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from greatapi.conf.settings import Settings

        monkeypatch.setenv("GREATAPI_SECRET_KEY", "x" * 64)
        monkeypatch.delenv("GREATAPI_SESSION_COOKIE_SECURE", raising=False)

        monkeypatch.setenv("GREATAPI_DEBUG", "false")
        assert Settings(_env_file=None).session_cookie_secure is True  # type: ignore[call-arg]

        monkeypatch.setenv("GREATAPI_DEBUG", "true")
        assert Settings(_env_file=None).session_cookie_secure is False  # type: ignore[call-arg]

    def test_the_admin_path_is_normalised(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from greatapi.conf.settings import Settings

        monkeypatch.setenv("GREATAPI_SECRET_KEY", "x" * 64)
        monkeypatch.setenv("GREATAPI_ADMIN_PATH", "backoffice/")
        assert Settings(_env_file=None).admin_path == "/backoffice"  # type: ignore[call-arg]


class TestProjectTemplateContents:
    def test_the_template_tree_has_no_stray_python(self) -> None:
        """Templates must not be importable from the installed package."""
        for directory in (PROJECT_TEMPLATE_DIR, APP_TEMPLATE_DIR):
            stray = [p for p in directory.rglob("*.py") if p.name != "script.py.mako"]
            assert not stray, f"unrendered .py in {directory}: {stray}"

    def test_the_generated_gitignore_covers_the_env_file(self, tmp_path: Path) -> None:
        runner.invoke(cli_app, ["startproject", "shop", "-d", str(tmp_path / "shop")])
        ignored = (tmp_path / "shop" / ".gitignore").read_text()
        assert ".env" in ignored
        assert "*.db" in ignored
