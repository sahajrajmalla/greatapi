"""Shared fixtures.

Everything runs against in-memory SQLite with no network and no API key: the
``echo`` provider covers every AI path. A suite that needs credentials is a
suite contributors skip.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest

# Set before greatapi is imported anywhere, because Settings reads the
# environment the first time it is constructed.
os.environ.setdefault("GREATAPI_SECRET_KEY", "test-secret-key-not-used-anywhere-real")
os.environ.setdefault("GREATAPI_DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("GREATAPI_DEBUG", "false")
os.environ.setdefault("GREATAPI_JOBS_ENABLED", "false")
os.environ.setdefault("GREATAPI_AI_ENABLED", "true")
os.environ.setdefault("GREATAPI_SESSION_COOKIE_SECURE", "false")
os.environ.setdefault("GREATAPI_LOGIN_RATE_LIMIT_PER_MINUTE", "1000")

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from greatapi import GreatAPI
from greatapi.admin import registry as admin_registry
from greatapi.admin.builtins import register_builtin_admins
from greatapi.db.base import Base
from greatapi.db.models import User
from greatapi.db.session import configure_engine, dispose_engine, get_sessionmaker
from greatapi.jobs import registry as job_registry
from greatapi.keys.ratelimit import InMemoryRateLimiter, set_rate_limiter
from greatapi.keys.service import clear_spend_cache
from greatapi.security.passwords import hash_password

ADMIN_PASSWORD = "hunter2hunter2"


@pytest.fixture(autouse=True)
def _isolate() -> Iterator[None]:
    """Reset every process-wide registry between tests."""
    admin_registry.unregister_all()
    job_registry.clear_registry()
    set_rate_limiter(InMemoryRateLimiter())
    clear_spend_cache()
    register_builtin_admins.__globals__["_registered"] = False
    yield
    admin_registry.unregister_all()
    job_registry.clear_registry()
    clear_spend_cache()


@pytest.fixture(autouse=True)
async def _dispose_engine() -> AsyncIterator[None]:
    """Release the engine after every test, whoever configured it.

    A test that calls ``configure_engine`` without disposing leaves a live
    connection whose finaliser runs at some arbitrary later point -- and with
    ``filterwarnings = error`` that ResourceWarning fails whichever unrelated
    test happens to be running at the time.
    """
    yield
    await dispose_engine()


@pytest.fixture
async def engine(tmp_path: Any) -> AsyncIterator[Any]:
    """A fresh database per test, in a temporary file.

    Deliberately not ``:memory:``. An in-memory database lives inside a single
    connection, so anything that causes the pool to open a new one -- a session
    torn down mid-statement, a worker cancelled at an awkward moment -- silently
    yields an *empty* database and a baffling "no such table". A temp file
    costs microseconds and removes that whole class of flake.
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    created = configure_engine(url)
    async with created.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield created
    await dispose_engine()


@pytest.fixture
async def session(engine: Any) -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as db_session:
        yield db_session


@pytest.fixture
async def admin_user(session: AsyncSession) -> User:
    user = User(
        email="admin@example.com",
        username="admin",
        full_name="Ada Admin",
        hashed_password=hash_password(ADMIN_PASSWORD),
        is_admin=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
async def plain_user(session: AsyncSession) -> User:
    user = User(
        email="user@example.com",
        username="user",
        hashed_password=hash_password(ADMIN_PASSWORD),
        is_admin=False,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
def app(engine: Any) -> GreatAPI:
    """An application with the admin mounted and the job worker off."""
    return GreatAPI(title="Test", jobs=False, create_tables=False)


@pytest.fixture
async def client(app: GreatAPI) -> AsyncIterator[httpx.AsyncClient]:
    """An HTTP client that does not follow redirects, so they can be asserted."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", follow_redirects=False
    ) as http_client:
        yield http_client


@pytest.fixture
async def admin_client(
    client: httpx.AsyncClient, admin_user: User
) -> AsyncIterator[httpx.AsyncClient]:
    """A client already signed in as an administrator."""
    response = await client.post(
        "/admin/login", data={"username": admin_user.username, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 303, response.text
    yield client


def csrf_token(client: httpx.AsyncClient) -> str:
    """Read the CSRF nonce out of the signed session cookie."""
    from greatapi.security.tokens import decode_token

    raw = client.cookies.get("greatapi_session")
    assert raw, "not signed in"
    token: str = decode_token(raw, expected_type="session")["csrf"]
    return token
