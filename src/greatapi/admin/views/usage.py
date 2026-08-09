"""Token, cost and latency reporting for LLM traffic."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select
from starlette.responses import Response

from greatapi.admin.charts import Series, bar_chart, line_chart
from greatapi.admin.templating import render
from greatapi.db.base import utcnow
from greatapi.db.models import AgentRun, LLMCall, RunStatus
from greatapi.security.dependencies import AdminUser, DbSession

__all__ = ["usage_router"]

usage_router = APIRouter(include_in_schema=False)


@usage_router.get("/usage")
async def usage(
    request: Request,
    session: DbSession,
    user: AdminUser,
    days: int = Query(14, ge=1, le=90),
) -> Response:
    since = utcnow() - timedelta(days=days)

    totals = (
        await session.execute(
            select(
                func.count(LLMCall.id),
                func.coalesce(func.sum(LLMCall.total_tokens), 0),
                func.coalesce(func.sum(LLMCall.cost_usd), 0.0),
                func.coalesce(func.avg(LLMCall.latency_ms), 0.0),
            ).where(LLMCall.created_at >= since)
        )
    ).one()

    failures = await session.scalar(
        select(func.count(LLMCall.id)).where(
            LLMCall.created_at >= since, LLMCall.status == RunStatus.failed
        )
    )

    by_day = (
        await session.execute(
            select(
                func.date(LLMCall.created_at).label("day"),
                func.coalesce(func.sum(LLMCall.total_tokens), 0),
                func.coalesce(func.sum(LLMCall.cost_usd), 0.0),
            )
            .where(LLMCall.created_at >= since)
            .group_by("day")
            .order_by("day")
        )
    ).all()

    by_model = (
        await session.execute(
            select(
                LLMCall.model,
                func.count(LLMCall.id),
                func.coalesce(func.sum(LLMCall.total_tokens), 0),
                func.coalesce(func.sum(LLMCall.cost_usd), 0.0),
                func.coalesce(func.avg(LLMCall.latency_ms), 0.0),
            )
            .where(LLMCall.created_at >= since)
            .group_by(LLMCall.model)
            .order_by(func.sum(LLMCall.cost_usd).desc())
            .limit(12)
        )
    ).all()

    recent_runs = list(
        (
            await session.execute(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(10))
        ).scalars()
    )

    day_labels = [str(row[0]) for row in by_day]

    return render(
        request,
        "usage.html",
        {
            "days": days,
            "total_calls": totals[0],
            "total_tokens": int(totals[1]),
            "total_cost": float(totals[2]),
            "avg_latency": int(totals[3]),
            "failures": failures or 0,
            "tokens_chart": line_chart(
                Series(day_labels, [float(row[1]) for row in by_day]), unit=" tokens"
            ),
            "cost_chart": bar_chart(
                Series(day_labels, [float(row[2]) for row in by_day]), unit=" USD"
            ),
            "by_model": [
                {
                    "model": row[0],
                    "calls": row[1],
                    "tokens": int(row[2]),
                    "cost": float(row[3]),
                    "latency": int(row[4]),
                }
                for row in by_model
            ],
            "recent_runs": recent_runs,
        },
        user=user,
        active="usage",
    )
