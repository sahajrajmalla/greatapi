"""API keys: issuance, scopes, rate limits and spend caps."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from greatapi import GreatAPI
from greatapi.db.base import utcnow
from greatapi.db.models import APIKey, LLMCall, User
from greatapi.keys import KeyRejection, create_api_key, require_api_key, verify_api_key
from greatapi.keys.ratelimit import InMemoryRateLimiter
from greatapi.keys.service import hash_key, monthly_spend


class TestIssuance:
    async def test_only_the_digest_is_stored(self, session: AsyncSession) -> None:
        record, raw = await create_api_key(session, name="Mobile")

        assert raw.startswith("gapi_")
        # The random secret can itself contain "_", so the format must be
        # parsed with a maxsplit rather than a plain split.
        assert raw.split("_", 2)[1] == record.prefix
        assert record.hashed_key == hash_key(raw)
        assert raw not in record.hashed_key
        # The prefix identifies a key without being able to reveal it.
        assert record.prefix in raw
        assert len(record.hashed_key) == 64

    async def test_two_keys_never_collide(self, session: AsyncSession) -> None:
        _, first = await create_api_key(session, name="one")
        _, second = await create_api_key(session, name="two")
        assert first != second


class TestVerification:
    async def test_a_valid_key_resolves(self, session: AsyncSession) -> None:
        record, raw = await create_api_key(session, name="valid", scopes=["chat:write"])
        resolved = await verify_api_key(session, raw)
        assert isinstance(resolved, APIKey)
        assert resolved.id == record.id

    @pytest.mark.parametrize("bad", ["nonsense", "gapi_short", "gapi_aaaaaaaa_wrongsecret"])
    async def test_a_bad_key_is_rejected(self, session: AsyncSession, bad: str) -> None:
        outcome = await verify_api_key(session, bad)
        assert isinstance(outcome, KeyRejection)
        assert outcome.reason == "invalid"

    async def test_a_revoked_key_is_rejected(self, session: AsyncSession) -> None:
        record, raw = await create_api_key(session, name="revoked")
        record.is_active = False
        await session.commit()

        outcome = await verify_api_key(session, raw)
        assert isinstance(outcome, KeyRejection)
        assert outcome.reason == "inactive"

    async def test_an_expired_key_is_rejected(self, session: AsyncSession) -> None:
        _, raw = await create_api_key(
            session, name="expired", expires_at=utcnow() - timedelta(days=1)
        )
        outcome = await verify_api_key(session, raw)
        assert isinstance(outcome, KeyRejection)
        assert outcome.reason == "expired"


def build_app(*scopes: str) -> GreatAPI:
    app = GreatAPI(title="keys", admin=False, jobs=False, create_tables=False)

    @app.get("/protected")
    async def protected(key: APIKey = Depends(require_api_key(*scopes))) -> dict[str, str]:
        return {"key": key.name}

    return app


class TestDependency:
    async def _call(self, app: GreatAPI, headers: dict[str, str]) -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/protected", headers=headers)

    async def test_missing_key_is_401(self, engine: object) -> None:
        response = await self._call(build_app(), {})
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    async def test_bearer_token_works(self, session: AsyncSession) -> None:
        _, raw = await create_api_key(session, name="bearer", scopes=["chat:write"])
        response = await self._call(build_app("chat:write"), {"authorization": f"Bearer {raw}"})
        assert response.status_code == 200
        assert response.json() == {"key": "bearer"}

    async def test_x_api_key_header_works(self, session: AsyncSession) -> None:
        _, raw = await create_api_key(session, name="header", scopes=["chat:write"])
        response = await self._call(build_app("chat:write"), {"x-api-key": raw})
        assert response.status_code == 200

    async def test_missing_scope_is_403(self, session: AsyncSession) -> None:
        _, raw = await create_api_key(session, name="narrow", scopes=["jobs:read"])
        response = await self._call(build_app("chat:write"), {"x-api-key": raw})
        assert response.status_code == 403
        assert "chat:write" in response.json()["detail"]

    async def test_rate_limit_is_429_with_retry_after(self, session: AsyncSession) -> None:
        _, raw = await create_api_key(session, name="limited", rate_limit_per_minute=2)
        app = build_app()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"x-api-key": raw}
            assert (await client.get("/protected", headers=headers)).status_code == 200
            assert (await client.get("/protected", headers=headers)).status_code == 200

            third = await client.get("/protected", headers=headers)
            assert third.status_code == 429
            assert int(third.headers["retry-after"]) >= 1

    async def test_exhausted_budget_is_402(self, session: AsyncSession) -> None:
        record, raw = await create_api_key(session, name="budget", monthly_budget_usd=1.0)
        session.add(
            LLMCall(
                provider="echo",
                model="echo:demo",
                total_tokens=10,
                cost_usd=1.5,
                api_key_id=record.id,
            )
        )
        await session.commit()

        response = await self._call(build_app(), {"x-api-key": raw})
        assert response.status_code == 402
        assert "budget" in response.json()["detail"].lower()

    async def test_last_used_is_recorded(self, session: AsyncSession) -> None:
        record, raw = await create_api_key(session, name="tracked")
        assert record.last_used_at is None

        await self._call(build_app(), {"x-api-key": raw})
        await session.refresh(record)
        assert record.last_used_at is not None


class TestSpend:
    async def test_only_this_month_and_this_key_count(self, session: AsyncSession) -> None:
        record, _ = await create_api_key(session, name="spender")
        other, _ = await create_api_key(session, name="other")

        start_of_month = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        session.add_all(
            [
                LLMCall(provider="e", model="m", cost_usd=0.25, api_key_id=record.id),
                LLMCall(provider="e", model="m", cost_usd=0.50, api_key_id=record.id),
                LLMCall(provider="e", model="m", cost_usd=9.99, api_key_id=other.id),
                LLMCall(
                    provider="e",
                    model="m",
                    cost_usd=100.0,
                    api_key_id=record.id,
                    created_at=start_of_month - timedelta(days=1),
                ),
            ]
        )
        await session.commit()

        assert await monthly_spend(session, record.id, use_cache=False) == pytest.approx(0.75)


class TestRateLimiter:
    async def test_window_slides(self) -> None:
        limiter = InMemoryRateLimiter()
        assert await limiter.hit("k", 2, 60.0) is None
        assert await limiter.hit("k", 2, 60.0) is None

        retry_after = await limiter.hit("k", 2, 60.0)
        assert retry_after is not None and 0 < retry_after <= 60.0

    async def test_keys_are_independent(self) -> None:
        limiter = InMemoryRateLimiter()
        assert await limiter.hit("a", 1, 60.0) is None
        assert await limiter.hit("b", 1, 60.0) is None
        assert await limiter.hit("a", 1, 60.0) is not None


class TestAdminPage:
    async def test_the_plaintext_key_is_shown_once_then_never(
        self, admin_client: httpx.AsyncClient, admin_user: User
    ) -> None:
        from greatapi.security.csrf import CSRF_FIELD_NAME
        from tests.conftest import csrf_token

        created = await admin_client.post(
            "/admin/api-keys",
            data={"name": "Shown once", CSRF_FIELD_NAME: csrf_token(admin_client)},
        )
        assert created.status_code == 303

        location = created.headers["location"]
        assert "key=gapi_" in location, "the secret is handed over exactly once"

        secret = location.split("key=")[1].split("&")[0]

        # Re-loading the page without the query parameter must not reveal it.
        # The prefix is still shown -- it names the key without unlocking it.
        plain = await admin_client.get("/admin/api-keys")
        assert plain.status_code == 200
        assert secret not in plain.text
        assert secret.split("_", 2)[2] not in plain.text
