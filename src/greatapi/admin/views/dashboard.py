"""The admin landing page."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from starlette.responses import Response

from greatapi.admin.charts import sparkline
from greatapi.admin.registry import get_registry
from greatapi.admin.templating import render
from greatapi.conf.settings import get_settings
from greatapi.db.base import utcnow
from greatapi.db.models import AuditLog, Job, JobStatus, LLMCall
from greatapi.security.dependencies import AdminUser, DbSession

__all__ = ["dashboard"]


# Registered directly onto the prefixed admin router rather than via
# `include_router`, which rejects an empty prefix paired with an empty path.
# This is what keeps the dashboard at `/admin` instead of `/admin/`.
async def dashboard(request: Request, session: DbSession, user: AdminUser) -> Response:
    """The admin landing page."""
    settings = get_settings()
    since = utcnow() - timedelta(days=7)

    recent_activity = list(
        (
            await session.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(8))
        ).scalars()
    )

    job_counts: dict[JobStatus, int] = {
        row[0]: row[1]
        for row in (
            await session.execute(select(Job.status, func.count()).group_by(Job.status))
        ).all()
    }

    tiles: list[dict[str, Any]] = []
    for group, admins in get_registry().by_group().items():
        for model_admin in admins:
            total = await session.scalar(select(func.count()).select_from(model_admin.model))
            tiles.append(
                {
                    "label": model_admin.label,
                    "group": group,
                    "slug": model_admin.slug,
                    "count": total or 0,
                }
            )
    tiles.sort(key=lambda tile: (-tile["count"], tile["label"]))

    context: dict[str, Any] = {
        "tiles": tiles,
        "recent_activity": recent_activity,
        "job_counts": {
            "queued": job_counts.get(JobStatus.queued, 0),
            "running": job_counts.get(JobStatus.running, 0),
            "failed": job_counts.get(JobStatus.failed, 0),
            "succeeded": job_counts.get(JobStatus.succeeded, 0),
        },
    }

    if settings.ai_enabled:
        totals = (
            await session.execute(
                select(
                    func.count(LLMCall.id),
                    func.coalesce(func.sum(LLMCall.total_tokens), 0),
                    func.coalesce(func.sum(LLMCall.cost_usd), 0.0),
                ).where(LLMCall.created_at >= since)
            )
        ).one()
        daily = (
            await session.execute(
                select(
                    func.date(LLMCall.created_at).label("day"),
                    func.coalesce(func.sum(LLMCall.total_tokens), 0),
                )
                .where(LLMCall.created_at >= since)
                .group_by("day")
                .order_by("day")
            )
        ).all()
        context |= {
            "ai_calls": totals[0],
            "ai_tokens": int(totals[1]),
            "ai_cost": float(totals[2]),
            "ai_sparkline": sparkline([float(row[1]) for row in daily]),
        }

    return render(request, "dashboard.html", context, user=user, active="dashboard")
