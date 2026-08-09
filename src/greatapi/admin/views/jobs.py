"""Job queue monitoring."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from starlette.responses import Response

from greatapi.admin.templating import flash_url, paginate, render
from greatapi.conf.settings import get_settings
from greatapi.db.base import utcnow
from greatapi.db.models import Job, JobStatus
from greatapi.jobs.registry import registered_jobs
from greatapi.security.dependencies import AdminUser, DbSession

__all__ = ["jobs_admin_router"]

jobs_admin_router = APIRouter(include_in_schema=False)


@jobs_admin_router.get("/jobs")
async def job_list(
    request: Request,
    session: DbSession,
    user: AdminUser,
    page: int = Query(1, ge=1),
    job_status: str = Query("", alias="status"),
) -> Response:
    settings = get_settings()
    size = settings.admin_page_size

    query = select(Job)
    if job_status and job_status in JobStatus.__members__:
        query = query.where(Job.status == JobStatus[job_status])

    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = list(
        (
            await session.execute(
                query.order_by(Job.created_at.desc()).offset((page - 1) * size).limit(size)
            )
        ).scalars()
    )

    counts: dict[JobStatus, int] = {
        row[0]: row[1]
        for row in (
            await session.execute(select(Job.status, func.count()).group_by(Job.status))
        ).all()
    }

    return render(
        request,
        "jobs.html",
        {
            "page": paginate(rows, int(total or 0), page, size),
            "status_filter": job_status,
            "statuses": [item.value for item in JobStatus],
            "counts": {item.value: counts.get(item, 0) for item in JobStatus},
            "handlers": sorted(registered_jobs()),
        },
        user=user,
        active="jobs",
    )


@jobs_admin_router.post("/jobs/{job_id}/retry")
async def retry_job(session: DbSession, user: AdminUser, job_id: int) -> Response:
    settings = get_settings()
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such job.")
    if job.status not in {JobStatus.failed, JobStatus.cancelled}:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Only failed or cancelled jobs can be retried."
        )

    job.status = JobStatus.queued
    job.run_at = utcnow()
    job.error = None
    job.finished_at = None
    job.max_attempts = max(job.max_attempts, job.attempts + 1)
    await session.commit()

    return RedirectResponse(
        flash_url(f"{settings.admin_path}/jobs", "job-retried"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@jobs_admin_router.post("/jobs/{job_id}/cancel")
async def cancel_job(session: DbSession, user: AdminUser, job_id: int) -> Response:
    settings = get_settings()
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such job.")
    if job.status != JobStatus.queued:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only queued jobs can be cancelled.")

    job.status = JobStatus.cancelled
    job.finished_at = utcnow()
    await session.commit()

    return RedirectResponse(f"{settings.admin_path}/jobs", status_code=status.HTTP_303_SEE_OTHER)
