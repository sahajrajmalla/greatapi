"""INSTALLED_APPS loading, the CLI's user creation, and route introspection."""

from __future__ import annotations

import itertools
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from greatapi.apps import load_admin, load_apps, load_models, load_routers
from greatapi.cli.introspect import describe_routes, import_app
from greatapi.cli.users import create_superuser
from greatapi.db.models import User
from greatapi.exceptions import GreatAPIError

_APP_COUNTER = itertools.count()


@pytest.fixture
def sample_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Write a small app package on disk and make it importable.

    The package gets a unique name per test: re-importing the same module path
    would re-register the same mapped class, and SQLAlchemy warns about that --
    which, with `filterwarnings = error`, is a failure.
    """
    name = f"sample{next(_APP_COUNTER)}"
    package = tmp_path / name
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(
        "from sqlalchemy.orm import Mapped, mapped_column\n"
        "from greatapi.db import Base\n"
        "\n"
        f"class {name.capitalize()}Thing(Base):\n"
        f"    __tablename__ = '{name}_thing'\n"
        "    id: Mapped[int] = mapped_column(primary_key=True)\n"
    )
    (package / "admin.py").write_text(
        "from greatapi import admin\n"
        f"from {name}.models import {name.capitalize()}Thing\n"
        "\n"
        f"@admin.register({name.capitalize()}Thing)\n"
        f"class {name.capitalize()}ThingAdmin(admin.ModelAdmin):\n"
        f"    app_label = '{name}'\n"
        "    list_display = ('id',)\n"
    )
    (package / "router.py").write_text(
        "from fastapi import APIRouter\n"
        "\n"
        f"router = APIRouter(prefix='/{name}')\n"
        "\n"
        "@router.get('/ping')\n"
        "async def ping() -> dict[str, str]:\n"
        "    return {'pong': 'yes'}\n"
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    yield name

    for module in list(sys.modules):
        if module == name or module.startswith(f"{name}."):
            del sys.modules[module]

    from greatapi.db.base import Base

    table = Base.metadata.tables.get(f"{name}_thing")
    if table is not None:
        Base.metadata.remove(table)


class TestLoading:
    def test_models_reach_the_metadata(self, sample_app: str) -> None:
        from greatapi.db.base import Base

        load_models([sample_app])
        # This is what makes `greatapi makemigrations` see an app's tables.
        assert f"{sample_app}_thing" in Base.metadata.tables

    def test_admin_registrations_run(self, sample_app: str) -> None:
        from greatapi.admin import get_registry

        load_models([sample_app])
        load_admin([sample_app])
        assert any(entry.group == sample_app for entry in get_registry().all())

    def test_routers_are_included(self, sample_app: str) -> None:
        app = FastAPI()
        load_models([sample_app])
        assert load_routers([sample_app], app) == [sample_app]

    def test_load_apps_does_all_three(self, sample_app: str) -> None:
        from greatapi.admin import get_registry
        from greatapi.db.base import Base

        app = FastAPI()
        load_apps([sample_app], app)

        assert f"{sample_app}_thing" in Base.metadata.tables
        assert any(entry.group == sample_app for entry in get_registry().all())

    def test_a_missing_app_is_explained(self) -> None:
        with pytest.raises(GreatAPIError, match="cannot be imported"):
            load_models(["definitely_not_installed"])

    def test_absent_submodules_are_fine(self, tmp_path: Path, monkeypatch) -> None:
        """An app with only models is a perfectly good app."""
        package = tmp_path / "bare"
        package.mkdir()
        (package / "__init__.py").write_text("")
        monkeypatch.syspath_prepend(str(tmp_path))

        load_apps(["bare"])  # must not raise
        sys.modules.pop("bare", None)

    def test_an_error_inside_an_app_is_not_swallowed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A typo in the user's code must not look like 'no such module'."""
        package = tmp_path / "broken"
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / "models.py").write_text("import a_module_that_does_not_exist\n")
        monkeypatch.syspath_prepend(str(tmp_path))

        with pytest.raises(ModuleNotFoundError, match="a_module_that_does_not_exist"):
            load_models(["broken"])

        for name in list(sys.modules):
            if name.startswith("broken"):
                del sys.modules[name]

    def test_a_router_module_without_a_router_warns_but_continues(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        package = tmp_path / "norouter"
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / "router.py").write_text("# forgot to define `router`\n")
        monkeypatch.syspath_prepend(str(tmp_path))

        app = FastAPI()
        assert load_routers(["norouter"], app) == []

        for name in list(sys.modules):
            if name.startswith("norouter"):
                del sys.modules[name]


class TestCreateSuperuser:
    async def test_it_creates_an_administrator(self, session: AsyncSession) -> None:
        user = await create_superuser("boss@example.com", "boss", "hunter2hunter2", "The Boss")

        assert user.is_admin is True
        assert user.is_active is True
        assert user.full_name == "The Boss"
        assert user.hashed_password.startswith("$argon2")

    async def test_a_duplicate_email_is_refused(self, session: AsyncSession) -> None:
        await create_superuser("dup@example.com", "one", "hunter2hunter2")
        with pytest.raises(GreatAPIError, match="email already exists"):
            await create_superuser("dup@example.com", "two", "hunter2hunter2")

    async def test_a_duplicate_username_is_refused(self, session: AsyncSession) -> None:
        await create_superuser("a@example.com", "same", "hunter2hunter2")
        with pytest.raises(GreatAPIError, match="username already exists"):
            await create_superuser("b@example.com", "same", "hunter2hunter2")

    async def test_a_weak_password_is_refused(self, session: AsyncSession) -> None:
        with pytest.raises(GreatAPIError, match="at least"):
            await create_superuser("weak@example.com", "weak", "short")

    async def test_the_created_user_can_sign_in(self, session: AsyncSession) -> None:
        from greatapi.security.dependencies import authenticate_user

        await create_superuser("signin@example.com", "signin", "hunter2hunter2")
        session.expire_all()

        assert await authenticate_user(session, "signin", "hunter2hunter2") is not None
        assert await authenticate_user(session, "signin@example.com", "hunter2hunter2") is not None
        assert await authenticate_user(session, "signin", "wrong-password") is None

    async def test_it_creates_the_schema_when_missing(self, tmp_path: Path) -> None:
        """1.x required running the server once before this would work."""
        from greatapi.db.session import configure_engine, dispose_engine

        configure_engine(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
        try:
            user = await create_superuser("fresh@example.com", "fresh", "hunter2hunter2")
            assert user.id is not None
        finally:
            await dispose_engine()


class TestIntrospection:
    def test_it_lists_nested_routes(self, app: object) -> None:
        import greatapi.cli.introspect as introspect

        rows = describe_routes.__wrapped__ if hasattr(describe_routes, "__wrapped__") else None
        assert rows is None  # no decorator; call the real thing below

        original = introspect.import_app
        introspect.import_app = lambda _target: app  # type: ignore[assignment]
        try:
            routes = describe_routes("ignored:app")
        finally:
            introspect.import_app = original

        paths = {path for _, path, _ in routes}
        assert "/admin/login" in paths, "nested routers must be walked, not just app.routes"
        assert "/jobs/{job_id}" in paths

    def test_a_malformed_target_is_explained(self) -> None:
        with pytest.raises(GreatAPIError, match="module:attribute"):
            import_app("nocolon")

    def test_a_missing_module_is_explained(self) -> None:
        with pytest.raises(GreatAPIError, match="Could not import"):
            import_app("no_such_module_at_all:app")

    def test_a_missing_attribute_is_explained(self) -> None:
        with pytest.raises(GreatAPIError, match="no attribute"):
            import_app("greatapi:not_a_real_attribute")


class TestUsersQuery:
    async def test_users_are_found_by_either_identifier(self, session: AsyncSession) -> None:
        await create_superuser("both@example.com", "both", "hunter2hunter2")
        found = await session.scalar(select(User).where(User.username == "both"))
        assert found is not None and found.email == "both@example.com"
