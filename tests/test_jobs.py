"""The job queue: registration, claiming, retries and status."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from greatapi.db.base import utcnow
from greatapi.db.models import Job, JobStatus
from greatapi.jobs import UnknownJobError, enqueue, job, registered_jobs
from greatapi.jobs.queue import backoff_delay, claim_jobs
from greatapi.jobs.worker import Worker, run_job


class TestRegistration:
    def test_a_job_is_registered_under_its_name(self) -> None:
        @job("summarise")
        async def handler(document_id: int) -> str:
            return f"summary of {document_id}"

        assert "summarise" in registered_jobs()
        assert handler.__greatapi_job_name__ == "summarise"

    def test_the_function_name_is_the_default(self) -> None:
        @job()
        async def reindex() -> None: ...

        assert "reindex" in registered_jobs()

    def test_a_blocking_function_is_refused(self) -> None:
        """A sync handler would stall every other job in the worker."""
        with pytest.raises(TypeError, match="must be an async function"):

            @job("blocking")
            def handler() -> None: ...

    async def test_an_unregistered_name_cannot_be_enqueued(self) -> None:
        with pytest.raises(UnknownJobError, match="No job handler registered"):
            await enqueue("never-defined")


class TestEnqueue:
    async def test_enqueue_stores_the_payload(self, session: AsyncSession) -> None:
        @job("greet")
        async def handler(name: str) -> str:
            return f"hi {name}"

        record = await enqueue(handler, name="ada")
        assert record.status is JobStatus.queued
        assert record.payload == {"name": "ada"}
        assert record.max_attempts >= 1

    async def test_enqueue_accepts_the_name_as_a_string(self, session: AsyncSession) -> None:
        @job("by-name")
        async def handler() -> None: ...

        record = await enqueue("by-name")
        assert record.name == "by-name"

    async def test_a_future_job_is_not_due_yet(self, session: AsyncSession) -> None:
        @job("later")
        async def handler() -> None: ...

        await enqueue(handler, run_at=utcnow() + timedelta(hours=1))
        assert await claim_jobs(session, 10) == []


class TestClaiming:
    async def test_a_due_job_is_claimed_once(self, session: AsyncSession) -> None:
        @job("claimable")
        async def handler() -> None: ...

        await enqueue(handler)

        first = await claim_jobs(session, 10)
        assert len(first) == 1
        assert first[0].status is JobStatus.running
        assert first[0].attempts == 1

        # A second worker must not get the same job.
        assert await claim_jobs(session, 10) == []

    async def test_claiming_respects_the_limit(self, session: AsyncSession) -> None:
        @job("many")
        async def handler(index: int) -> None: ...

        for index in range(5):
            await enqueue(handler, index=index)

        assert len(await claim_jobs(session, 2)) == 2


class TestExecution:
    async def test_a_successful_job_records_its_result(self, session: AsyncSession) -> None:
        @job("adds")
        async def handler(a: int, b: int) -> int:
            return a + b

        await enqueue(handler, a=2, b=3)
        for claimed in await claim_jobs(session, 1):
            await run_job(claimed)

        record = (await session.execute(select(Job))).scalar_one()
        await session.refresh(record)
        assert record.status is JobStatus.succeeded
        assert record.result == 5
        assert record.finished_at is not None

    async def test_a_failure_is_retried_then_dead_lettered(self, session: AsyncSession) -> None:
        attempts = 0

        @job("flaky", max_attempts=2)
        async def handler() -> None:
            nonlocal attempts
            attempts += 1
            raise ValueError("nope")

        await enqueue(handler)

        # First attempt fails and is rescheduled.
        for claimed in await claim_jobs(session, 1):
            await run_job(claimed)
        record = (await session.execute(select(Job))).scalar_one()
        await session.refresh(record)
        assert record.status is JobStatus.queued
        assert record.attempts == 1
        assert "ValueError" in (record.error or "")

        # Make it due again, then exhaust the attempts.
        record.run_at = utcnow()
        await session.commit()
        for claimed in await claim_jobs(session, 1):
            await run_job(claimed)
        await session.refresh(record)

        assert attempts == 2
        assert record.status is JobStatus.failed, "should stop retrying at max_attempts"

    async def test_a_missing_handler_fails_the_job_rather_than_the_worker(
        self, session: AsyncSession
    ) -> None:
        @job("vanishing")
        async def handler() -> None: ...

        await enqueue(handler)
        claimed = (await claim_jobs(session, 1))[0]

        from greatapi.jobs import registry

        registry.clear_registry()  # simulate a worker without this handler
        await run_job(claimed)

        record = (await session.execute(select(Job))).scalar_one()
        await session.refresh(record)
        assert record.status is JobStatus.failed
        assert "No job handler registered" in (record.error or "")

    def test_backoff_grows_and_is_capped(self) -> None:
        assert backoff_delay(1) < backoff_delay(3) < backoff_delay(10)
        assert backoff_delay(1000) == timedelta(seconds=300)


class TestWorker:
    async def test_the_worker_drains_the_queue(self, session: AsyncSession) -> None:
        done = asyncio.Event()

        @job("worker-job")
        async def handler() -> str:
            done.set()
            return "ran"

        await enqueue(handler)

        worker = Worker(concurrency=2, poll_interval=0.01)
        worker.start()
        try:
            await asyncio.wait_for(done.wait(), timeout=3.0)
        finally:
            await worker.stop()

        record = (await session.execute(select(Job))).scalar_one()
        await session.refresh(record)
        assert record.status is JobStatus.succeeded


class TestStatusEndpoint:
    async def test_polling_a_job(self, admin_client: httpx.AsyncClient) -> None:
        @job("pollable")
        async def handler() -> None: ...

        record = await enqueue(handler)

        response = await admin_client.get(f"/jobs/{record.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "pollable"
        assert body["status"] == "queued"

    async def test_unknown_job_is_404(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/jobs/9999")).status_code == 404
