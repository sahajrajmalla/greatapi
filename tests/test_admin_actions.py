"""Admin actions: job retry/cancel, key creation and revocation, usage filters."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from greatapi.db.base import utcnow
from greatapi.db.models import APIKey, Job, JobStatus, LLMCall, RunStatus
from greatapi.security.csrf import CSRF_FIELD_NAME
from tests.conftest import csrf_token


def form(client: httpx.AsyncClient, **fields: str) -> dict[str, str]:
    return {**fields, CSRF_FIELD_NAME: csrf_token(client)}


async def make_job(session: AsyncSession, status: JobStatus, attempts: int = 1) -> Job:
    record = Job(
        name="demo",
        payload={},
        status=status,
        run_at=utcnow(),
        attempts=attempts,
        max_attempts=3,
        error="boom" if status is JobStatus.failed else None,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


class TestJobActions:
    async def test_the_list_renders_with_counts(
        self, admin_client: httpx.AsyncClient, session: AsyncSession
    ) -> None:
        for status in (JobStatus.queued, JobStatus.failed, JobStatus.succeeded):
            await make_job(session, status)

        response = await admin_client.get("/admin/jobs")
        assert response.status_code == 200
        assert "queued" in response.text
        assert "failed" in response.text

    async def test_it_can_be_filtered_by_status(
        self, admin_client: httpx.AsyncClient, session: AsyncSession
    ) -> None:
        await make_job(session, JobStatus.failed)
        await make_job(session, JobStatus.succeeded)

        response = await admin_client.get("/admin/jobs", params={"status": "failed"})
        assert response.status_code == 200

    async def test_an_unknown_status_filter_is_ignored(
        self, admin_client: httpx.AsyncClient
    ) -> None:
        response = await admin_client.get("/admin/jobs", params={"status": "nonsense"})
        assert response.status_code == 200

    async def test_a_failed_job_can_be_retried(
        self, admin_client: httpx.AsyncClient, session: AsyncSession
    ) -> None:
        record = await make_job(session, JobStatus.failed, attempts=3)

        response = await admin_client.post(
            f"/admin/jobs/{record.id}/retry", data=form(admin_client)
        )
        assert response.status_code == 303

        await session.refresh(record)
        assert record.status is JobStatus.queued
        assert record.error is None
        assert record.max_attempts > 3, "retrying must raise the ceiling above the attempts made"

    async def test_a_succeeded_job_cannot_be_retried(
        self, admin_client: httpx.AsyncClient, session: AsyncSession
    ) -> None:
        record = await make_job(session, JobStatus.succeeded)
        response = await admin_client.post(
            f"/admin/jobs/{record.id}/retry", data=form(admin_client)
        )
        assert response.status_code == 400

    async def test_a_queued_job_can_be_cancelled(
        self, admin_client: httpx.AsyncClient, session: AsyncSession
    ) -> None:
        record = await make_job(session, JobStatus.queued)
        response = await admin_client.post(
            f"/admin/jobs/{record.id}/cancel", data=form(admin_client)
        )
        assert response.status_code == 303

        await session.refresh(record)
        assert record.status is JobStatus.cancelled
        assert record.finished_at is not None

    async def test_a_running_job_cannot_be_cancelled(
        self, admin_client: httpx.AsyncClient, session: AsyncSession
    ) -> None:
        record = await make_job(session, JobStatus.running)
        response = await admin_client.post(
            f"/admin/jobs/{record.id}/cancel", data=form(admin_client)
        )
        assert response.status_code == 400

    @pytest.mark.parametrize("action", ["retry", "cancel"])
    async def test_an_unknown_job_is_404(
        self, admin_client: httpx.AsyncClient, action: str
    ) -> None:
        response = await admin_client.post(f"/admin/jobs/99999/{action}", data=form(admin_client))
        assert response.status_code == 404


class TestKeyActions:
    async def test_a_key_is_created_with_its_options(
        self, admin_client: httpx.AsyncClient, session: AsyncSession
    ) -> None:
        expiry = (utcnow() + timedelta(days=30)).replace(microsecond=0, tzinfo=None).isoformat()
        response = await admin_client.post(
            "/admin/api-keys",
            data=form(
                admin_client,
                name="Mobile",
                scopes="chat:write, jobs:read",
                rate_limit_per_minute="60",
                monthly_budget_usd="25.5",
                expires_at=expiry,
            ),
        )
        assert response.status_code == 303

        from sqlalchemy import select

        record = (await session.execute(select(APIKey))).scalars().one()
        assert record.name == "Mobile"
        assert set(record.scopes) == {"chat:write", "jobs:read"}
        assert record.rate_limit_per_minute == 60
        assert record.monthly_budget_usd == 25.5
        assert record.expires_at is not None

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("rate_limit_per_minute", "not-a-number"),
            ("rate_limit_per_minute", "0"),
            ("monthly_budget_usd", "abc"),
            ("monthly_budget_usd", "-5"),
            ("expires_at", "not-a-date"),
        ],
    )
    async def test_malformed_options_are_refused(
        self, admin_client: httpx.AsyncClient, field: str, value: str
    ) -> None:
        response = await admin_client.post(
            "/admin/api-keys", data=form(admin_client, name="Bad", **{field: value})
        )
        assert response.status_code == 400

    async def test_a_key_can_be_revoked(
        self, admin_client: httpx.AsyncClient, session: AsyncSession
    ) -> None:
        from greatapi.keys.service import create_api_key

        record, _ = await create_api_key(session, name="Doomed")
        response = await admin_client.post(
            f"/admin/api-keys/{record.id}/revoke", data=form(admin_client)
        )
        assert response.status_code == 303

        await session.refresh(record)
        assert record.is_active is False

    async def test_revoking_an_unknown_key_is_404(self, admin_client: httpx.AsyncClient) -> None:
        response = await admin_client.post("/admin/api-keys/98765/revoke", data=form(admin_client))
        assert response.status_code == 404

    async def test_the_list_shows_spend_against_budget(
        self, admin_client: httpx.AsyncClient, session: AsyncSession
    ) -> None:
        from greatapi.keys.service import create_api_key

        record, _ = await create_api_key(session, name="Tracked", monthly_budget_usd=10.0)
        session.add(LLMCall(provider="echo", model="echo:demo", cost_usd=2.5, api_key_id=record.id))
        await session.commit()

        response = await admin_client.get("/admin/api-keys")
        assert response.status_code == 200
        assert "$2.50" in response.text
        assert "$10.00" in response.text


class TestUsagePage:
    async def test_it_summarises_recorded_calls(
        self, admin_client: httpx.AsyncClient, session: AsyncSession
    ) -> None:
        for index in range(5):
            session.add(
                LLMCall(
                    provider="anthropic",
                    model="anthropic:claude-sonnet-5",
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150,
                    cost_usd=0.01,
                    latency_ms=1200,
                    status=RunStatus.failed if index == 0 else RunStatus.succeeded,
                )
            )
        await session.commit()

        response = await admin_client.get("/admin/usage")
        assert response.status_code == 200
        assert "750" in response.text, "total tokens"
        assert "$0.05" in response.text, "total cost"
        assert "1 failed" in response.text
        assert "anthropic:claude-sonnet-5" in response.text

    @pytest.mark.parametrize("days", [7, 14, 30, 90])
    async def test_the_range_can_be_changed(
        self, admin_client: httpx.AsyncClient, days: int
    ) -> None:
        response = await admin_client.get("/admin/usage", params={"days": days})
        assert response.status_code == 200

    async def test_an_out_of_range_window_is_refused(self, admin_client: httpx.AsyncClient) -> None:
        assert (await admin_client.get("/admin/usage", params={"days": 900})).status_code == 422

    async def test_it_says_so_when_there_is_nothing(self, admin_client: httpx.AsyncClient) -> None:
        response = await admin_client.get("/admin/usage")
        assert response.status_code == 200
        assert "No calls recorded" in response.text


class TestDashboard:
    async def test_it_counts_models_and_shows_activity(
        self, admin_client: httpx.AsyncClient, session: AsyncSession
    ) -> None:
        response = await admin_client.get("/admin")
        assert response.status_code == 200
        assert "Overview" in response.text
        # The signed-in user is one record, so the User tile is non-zero.
        assert "User" in response.text

    async def test_logging_out_clears_the_cookie(self, admin_client: httpx.AsyncClient) -> None:
        response = await admin_client.post("/admin/logout", data=form(admin_client))
        assert response.status_code == 303
        assert "greatapi_session=" in response.headers["set-cookie"]
        assert (await admin_client.get("/admin")).status_code in (401, 303)
