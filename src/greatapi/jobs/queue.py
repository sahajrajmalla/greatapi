"""Enqueuing and claiming jobs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from greatapi.conf.settings import get_settings
from greatapi.db.base import utcnow
from greatapi.db.models import Job, JobStatus
from greatapi.db.session import session_scope
from greatapi.jobs.registry import get_handler

__all__ = ["backoff_delay", "claim_jobs", "enqueue", "get_job"]

#: Retry schedule: 1s, 4s, 9s, ... capped at five minutes.
_MAX_BACKOFF_SECONDS = 300


def backoff_delay(attempts: int) -> timedelta:
    return timedelta(seconds=min(attempts**2, _MAX_BACKOFF_SECONDS))


async def enqueue(
    job: str | Callable[..., Any],
    *,
    run_at: datetime | None = None,
    max_attempts: int | None = None,
    session: AsyncSession | None = None,
    **payload: Any,
) -> Job:
    """Queue a job for the worker.

    Accepts either the registered name or the decorated function itself.
    Returns immediately; poll ``GET /jobs/{id}`` for the outcome.
    """
    name = job if isinstance(job, str) else getattr(job, "__greatapi_job_name__", job.__name__)
    handler = get_handler(name)
    settings = get_settings()

    record = Job(
        name=name,
        payload=payload,
        status=JobStatus.queued,
        run_at=run_at or utcnow(),
        max_attempts=max_attempts or handler.max_attempts or settings.jobs_default_max_attempts,
    )

    if session is not None:
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record

    async with session_scope() as scoped:
        scoped.add(record)
        await scoped.flush()
        await scoped.refresh(record)
        return record


async def get_job(session: AsyncSession, job_id: int) -> Job | None:
    return await session.get(Job, job_id)


async def claim_jobs(session: AsyncSession, limit: int) -> list[Job]:
    """Atomically take up to ``limit`` due jobs.

    Postgres uses ``FOR UPDATE SKIP LOCKED``. SQLite has no such clause, so the
    claim is confirmed by a conditional ``UPDATE`` whose row count tells us
    whether this worker won the race -- correct on both, without a dialect
    branch in the hot path.
    """
    dialect = session.get_bind().dialect.name
    now = utcnow()

    query = (
        select(Job.id)
        .where(Job.status == JobStatus.queued, Job.run_at <= now)
        .order_by(Job.run_at)
        .limit(limit)
    )
    if dialect == "postgresql":
        query = query.with_for_update(skip_locked=True)

    candidate_ids = list((await session.execute(query)).scalars())
    if not candidate_ids:
        return []

    claimed: list[int] = []
    for job_id in candidate_ids:
        result = cast(
            CursorResult[Any],
            await session.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == JobStatus.queued)
                .values(status=JobStatus.running, started_at=now, attempts=Job.attempts + 1)
            ),
        )
        # rowcount is how we learn whether *this* worker won the claim.
        if result.rowcount == 1:
            claimed.append(job_id)
    await session.commit()

    if not claimed:
        return []
    return list((await session.execute(select(Job).where(Job.id.in_(claimed)))).scalars())
