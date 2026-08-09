"""The in-process job worker.

Runs as an asyncio task inside the application, so a plain ``greatapi
runserver`` gives you working background jobs with no extra infrastructure. It
is deliberately behind a small surface (:func:`start_worker` / the ``Job``
table), so a Redis- or ARQ-backed worker can replace it without any change to
``@job`` or :func:`enqueue`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import traceback
from datetime import timedelta
from typing import Any

from greatapi.conf.settings import get_settings
from greatapi.db.base import utcnow
from greatapi.db.models import Job, JobStatus
from greatapi.db.session import session_scope
from greatapi.jobs.queue import backoff_delay, claim_jobs
from greatapi.jobs.registry import UnknownJobError, get_handler

__all__ = ["Worker", "run_job"]

logger = logging.getLogger("greatapi.jobs")


async def run_job(job: Job) -> None:
    """Execute one claimed job and record the outcome."""
    try:
        handler = get_handler(job.name)
        result = await handler.func(**job.payload)
    except UnknownJobError as exc:
        await _finish(job.id, status=JobStatus.failed, error=str(exc))
        logger.error("Job %s (#%s) has no handler in this process", job.name, job.id)
    except asyncio.CancelledError:
        # Shutdown mid-flight: put it back so another worker picks it up.
        # Shielded, because an await inside a cancelled task is itself
        # cancelled -- without this the job would be left stuck in `running`.
        with contextlib.suppress(Exception):
            await asyncio.shield(_requeue(job.id, delay_seconds=0))
        raise
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        if job.attempts < job.max_attempts:
            delay = backoff_delay(job.attempts)
            await _requeue(job.id, delay_seconds=delay.total_seconds(), error=message)
            logger.warning(
                "Job %s (#%s) failed on attempt %s/%s, retrying in %ss",
                job.name,
                job.id,
                job.attempts,
                job.max_attempts,
                int(delay.total_seconds()),
            )
        else:
            await _finish(job.id, status=JobStatus.failed, error=message)
            logger.error("Job %s (#%s) failed permanently", job.name, job.id)
    else:
        await _finish(job.id, status=JobStatus.succeeded, result=result)
        logger.info("Job %s (#%s) succeeded", job.name, job.id)


async def _finish(
    job_id: int, *, status: JobStatus, result: Any = None, error: str | None = None
) -> None:
    async with session_scope() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.status = status
        job.error = error
        job.finished_at = utcnow()
        if result is not None:
            job.result = _jsonable(result)


async def _requeue(job_id: int, *, delay_seconds: float, error: str | None = None) -> None:
    async with session_scope() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.queued
        job.error = error
        job.started_at = None
        job.run_at = utcnow() + timedelta(seconds=delay_seconds)


def _jsonable(value: Any) -> Any:
    """Results are stored as JSON, so fall back to ``repr`` for exotic types."""
    if isinstance(value, str | int | float | bool | list | dict) or value is None:
        return value
    return repr(value)


class Worker:
    """Polls for due jobs and runs up to ``concurrency`` of them at a time."""

    def __init__(self, *, concurrency: int | None = None, poll_interval: float | None = None):
        settings = get_settings()
        self.concurrency = concurrency or settings.jobs_worker_concurrency
        self.poll_interval = poll_interval or settings.jobs_poll_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._idle = asyncio.Event()
        self._idle.set()

    async def _tick(self) -> int:
        async with session_scope() as session:
            jobs = await claim_jobs(session, self.concurrency)
        if not jobs:
            return 0

        self._idle.clear()
        try:
            await asyncio.gather(*(run_job(job) for job in jobs))
        finally:
            self._idle.set()
        return len(jobs)

    async def run(self) -> None:
        logger.info("Job worker started (concurrency=%s)", self.concurrency)
        try:
            while not self._stopping.is_set():
                try:
                    processed = await self._tick()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Job worker tick failed; continuing")
                    processed = 0
                # Only sleep when the queue was empty, so a backlog drains fast.
                if processed == 0:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._stopping.wait(), self.poll_interval)
        except asyncio.CancelledError:
            logger.info("Job worker cancelled")
            raise
        logger.info("Job worker stopped")

    def start(self) -> asyncio.Task[None]:
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self.run(), name="greatapi-job-worker")
        return self._task

    async def stop(self, timeout: float = 10.0) -> None:
        """Stop after the jobs already in flight finish.

        Cancelling outright would tear down whatever session the current job
        holds mid-statement -- which, on a pooled connection, can leave the
        pool handing out a connection that was never cleanly closed.
        """
        if self._task is None:
            return

        self._stopping.set()
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout)
        except TimeoutError:
            logger.warning("Job worker did not stop within %ss; cancelling", timeout)
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        except asyncio.CancelledError:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        finally:
            self._task = None
