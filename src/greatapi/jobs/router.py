"""Public job status endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from greatapi.db.models import Job, JobStatus
from greatapi.security.dependencies import DbSession

__all__ = ["JobRead", "jobs_router"]

jobs_router = APIRouter(prefix="/jobs", tags=["Jobs"])


class JobRead(BaseModel):
    """The status of a queued job."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: JobStatus
    attempts: int
    max_attempts: int
    result: object | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


@jobs_router.get("/{job_id}", response_model=JobRead, summary="Poll a job's status")
async def read_job(job_id: int, session: DbSession) -> Job:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No job with id {job_id}.")
    return job
