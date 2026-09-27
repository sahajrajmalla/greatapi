"""The ``greatapi`` command line."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from greatapi import __version__
from greatapi.cli.scaffold import (
    APP_TEMPLATE_DIR,
    PROJECT_TEMPLATE_DIR,
    generate_secret_key,
    register_app,
    render_tree,
    validate_name,
)
from greatapi.exceptions import GreatAPIError

__all__ = ["app", "main"]

app = typer.Typer(
    name="greatapi",
    help="The batteries-included FastAPI framework.",
    no_args_is_help=True,
    add_completion=True,
)


def _fail(message: str) -> None:
    typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def _ok(message: str) -> None:
    typer.secho(message, fg=typer.colors.GREEN)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"greatapi {__version__}")
        raise typer.Exit


@app.callback()
def cli(
    version: Annotated[
        bool,
        typer.Option(
            "--version", "-V", callback=_version_callback, is_eager=True, help="Show the version."
        ),
    ] = False,
) -> None:
    """GreatAPI command line."""
    # The project root is where commands are run from, and its modules have to
    # be importable for `runserver`, `makemigrations` and app loading to work.
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)


# ---------------------------------------------------------------- scaffolding


@app.command()
def startproject(
    name: Annotated[str, typer.Argument(help="Project name; must be a valid Python identifier.")],
    directory: Annotated[
        Path | None,
        typer.Option("--directory", "-d", help="Where to create it. Defaults to ./<name>."),
    ] = None,
) -> None:
    """Create a new project that runs immediately."""
    try:
        validate_name(name, "project")
    except GreatAPIError as exc:
        _fail(str(exc))

    target = directory or Path.cwd() / name
    if target.exists() and any(target.iterdir()):
        _fail(f"{target} already exists and is not empty.")

    context = {"project_name": name, "secret_key": generate_secret_key()}
    try:
        render_tree(PROJECT_TEMPLATE_DIR, target, context)
    except OSError as exc:
        _fail(f"Could not write to {target}: {exc}")

    _ok(f"Created project {name} in {target}")
    typer.echo(
        "\nNext:\n"
        f"  cd {target.name}\n"
        "  greatapi migrate\n"
        "  greatapi createsuperuser\n"
        "  greatapi runserver\n\n"
        "Then open http://127.0.0.1:8000/admin"
    )


@app.command()
def startapp(
    name: Annotated[str, typer.Argument(help="App name; must be a valid Python identifier.")],
) -> None:
    """Create an app and register it in INSTALLED_APPS."""
    try:
        validate_name(name, "app")
    except GreatAPIError as exc:
        _fail(str(exc))

    target = Path.cwd() / name
    if target.exists() and any(target.iterdir()):
        _fail(f"{target} already exists and is not empty.")

    render_tree(APP_TEMPLATE_DIR, target, {"app_name": name})
    _ok(f"Created app {name}")

    registered = False
    for candidate in sorted(Path.cwd().glob("*/settings.py")):
        if register_app(candidate, name):
            registered = True
            typer.echo(f"  registered in {candidate.relative_to(Path.cwd())}")
            break

    if not registered:
        typer.secho(
            f'  could not find INSTALLED_APPS; add "{name}" to it yourself.',
            fg=typer.colors.YELLOW,
        )

    typer.echo(
        f"\nDefine models in {name}/models.py, routes in {name}/router.py, "
        f"and admin classes in {name}/admin.py.\n"
        f"Then:  greatapi makemigrations -m 'add {name}' && greatapi migrate"
    )


@app.command(name="generate-secret")
def generate_secret() -> None:
    """Print a fresh signing key for GREATAPI_SECRET_KEY."""
    typer.echo(generate_secret_key())


# ---------------------------------------------------------------- running


@app.command()
def runserver(
    host: Annotated[str, typer.Option(help="Interface to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to bind.")] = 8000,
    reload: Annotated[bool, typer.Option(help="Restart on code changes.")] = True,
    workers: Annotated[int | None, typer.Option(help="Worker processes. Disables reload.")] = None,
    application: Annotated[str, typer.Option("--app", help="ASGI app to serve.")] = "main:app",
    log_level: Annotated[str, typer.Option(help="Uvicorn log level.")] = "info",
) -> None:
    """Run the development server.

    Calls uvicorn in-process rather than shelling out, so a missing dependency
    or an import error in your app produces a real traceback.
    """
    try:
        import uvicorn
    except ImportError:  # pragma: no cover - uvicorn is a base dependency
        _fail("uvicorn is not installed. Reinstall greatapi.")

    if workers and workers > 1 and reload:
        typer.secho("Reload is off when running multiple workers.", fg=typer.colors.YELLOW)
        reload = False

    typer.echo(f"Serving {application} on http://{host}:{port}  (admin at /admin)")
    uvicorn.run(
        application,
        host=host,
        port=port,
        reload=reload,
        workers=workers,
        log_level=log_level,
    )


@app.command()
def routes(
    application: Annotated[str, typer.Option("--app", help="ASGI app to inspect.")] = "main:app",
) -> None:
    """Print the route table."""
    from greatapi.cli.introspect import describe_routes

    try:
        for methods, path, name in describe_routes(application):
            typer.echo(f"{methods:<22} {path:<48} {name}")
    except GreatAPIError as exc:
        _fail(str(exc))


# ---------------------------------------------------------------- database


@app.command()
def migrate(
    revision: Annotated[str, typer.Argument(help="Target revision.")] = "head",
) -> None:
    """Apply migrations."""
    from alembic import command

    from greatapi.db.migrations import build_config

    try:
        command.upgrade(build_config(), revision)
    except GreatAPIError as exc:
        _fail(str(exc))
    _ok("Database is up to date.")


@app.command()
def makemigrations(
    message: Annotated[str, typer.Option("--message", "-m", help="What changed.")] = "auto",
    empty: Annotated[
        bool, typer.Option("--empty", help="Write a blank revision to fill in.")
    ] = False,
) -> None:
    """Generate a migration from changes to your models."""
    from alembic import command

    from greatapi.db.migrations import build_config

    try:
        command.revision(build_config(), message=message, autogenerate=not empty)
    except GreatAPIError as exc:
        _fail(str(exc))


@app.command()
def downgrade(
    revision: Annotated[str, typer.Argument(help="Target revision, e.g. -1.")] = "-1",
) -> None:
    """Roll migrations back."""
    from alembic import command

    from greatapi.db.migrations import build_config

    try:
        command.downgrade(build_config(), revision)
    except GreatAPIError as exc:
        _fail(str(exc))
    _ok(f"Rolled back to {revision}.")


@app.command()
def history() -> None:
    """Show the migration history."""
    from alembic import command

    from greatapi.db.migrations import build_config

    try:
        command.history(build_config(), indicate_current=True)
    except GreatAPIError as exc:
        _fail(str(exc))


# ---------------------------------------------------------------- users


@app.command()
def createsuperuser(
    email: Annotated[str | None, typer.Option(help="Email address.")] = None,
    username: Annotated[str | None, typer.Option(help="Username.")] = None,
    password: Annotated[str | None, typer.Option(help="Password. Prompted for if omitted.")] = None,
    full_name: Annotated[str | None, typer.Option(help="Display name.")] = None,
    noinput: Annotated[
        bool, typer.Option("--noinput", help="Never prompt. For scripts and CI.")
    ] = False,
) -> None:
    """Create an administrator."""
    from greatapi.cli.users import create_superuser

    if noinput:
        email = email or os.environ.get("GREATAPI_SUPERUSER_EMAIL")
        username = username or os.environ.get("GREATAPI_SUPERUSER_USERNAME")
        password = password or os.environ.get("GREATAPI_SUPERUSER_PASSWORD")
        if not (email and username and password):
            _fail(
                "--noinput needs --email, --username and --password "
                "(or GREATAPI_SUPERUSER_EMAIL / _USERNAME / _PASSWORD)."
            )
    else:
        email = email or typer.prompt("Email")
        username = username or typer.prompt("Username", default=email.split("@")[0])
        full_name = full_name or typer.prompt("Full name", default="", show_default=False)
        if not password:
            password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)

    assert email and username and password
    try:
        asyncio.run(create_superuser(email, username, password, full_name or None))
    except GreatAPIError as exc:
        _fail(str(exc))
    _ok(f"Created superuser {username!r}.")


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
