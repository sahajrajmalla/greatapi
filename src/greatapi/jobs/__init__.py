"""Durable background jobs.

Long-running work -- inference, batch imports, report generation -- outlives the
request that asked for it. ``BackgroundTasks`` cannot: it dies with the process
and leaves no trace. These jobs live in the database, survive restarts, retry
with backoff, and are visible in the admin.
"""

from __future__ import annotations

__all__ = [
    "Job",
    "JobStatus",
    "UnknownJobError",
    "Worker",
    "enqueue",
    "get_job",
    "job",
    "jobs_router",
    "registered_jobs",
    "run_job",
]

from greatapi.db.models import Job, JobStatus
from greatapi.jobs.queue import enqueue, get_job
from greatapi.jobs.registry import UnknownJobError, job, registered_jobs
from greatapi.jobs.router import jobs_router
from greatapi.jobs.worker import Worker, run_job
