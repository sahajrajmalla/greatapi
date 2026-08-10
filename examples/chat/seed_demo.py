"""Fill the demo with realistic data, so the admin has something to show.

Empty dashboards are hard to evaluate. This creates a fortnight of LLM calls
across three models, some agent runs, jobs in every state, an audit trail and a
couple of API keys.

    cd examples/chat
    python seed_demo.py

Safe to run repeatedly; it clears its own data first.
"""

from __future__ import annotations

import asyncio
import random
from datetime import timedelta

from app import Conversation  # the demo app's own model
from sqlalchemy import delete

from greatapi.db.base import utcnow
from greatapi.db.models import (
    AgentRun,
    APIKey,
    AuditAction,
    AuditLog,
    Job,
    JobStatus,
    LLMCall,
    RunStatus,
    User,
)
from greatapi.db.session import create_all, session_scope
from greatapi.keys.service import create_api_key
from greatapi.security.passwords import hash_password

MODELS = [
    ("anthropic", "anthropic:claude-sonnet-5", 3.0, 15.0),
    ("openai", "openai:gpt-5", 1.25, 10.0),
    ("local", "local:llama3.2", 0.0, 0.0),
]

PROMPTS = [
    "Summarise this quarter's support tickets",
    "Draft a release note for version 2.0",
    "Which customers churned last month, and why?",
    "Translate the onboarding email into French",
    "Explain this stack trace to a junior engineer",
    "Write a migration plan for the new schema",
]


async def main() -> None:
    random.seed(7)
    await create_all()

    async with session_scope() as session:
        # Start from a clean slate so re-running does not pile data up.
        for model in (LLMCall, AgentRun, Job, AuditLog, Conversation, APIKey):
            await session.execute(delete(model))

        # An account to sign in with, if `make demo` has not made one.
        existing = await session.get(User, 1)
        if existing is None:
            session.add(
                User(
                    email="demo@example.com",
                    username="demo",
                    full_name="Demo Admin",
                    hashed_password=hash_password("demopassword1"),
                    is_admin=True,
                )
            )
            await session.flush()

        # A fortnight of traffic, busier on weekdays.
        for day_offset in range(14):
            day = utcnow() - timedelta(days=13 - day_offset)
            volume = random.randint(3, 9) if day.weekday() < 5 else random.randint(1, 4)

            for _ in range(volume):
                provider, model, price_in, price_out = random.choice(MODELS)
                prompt_tokens = random.randint(300, 4000)
                completion_tokens = random.randint(100, 1500)
                failed = random.random() < 0.06

                session.add(
                    LLMCall(
                        provider=provider,
                        model=model,
                        operation=random.choice(["complete", "stream"]),
                        status=RunStatus.failed if failed else RunStatus.succeeded,
                        prompt_tokens=0 if failed else prompt_tokens,
                        completion_tokens=0 if failed else completion_tokens,
                        total_tokens=0 if failed else prompt_tokens + completion_tokens,
                        cost_usd=0.0
                        if failed
                        else (prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000,
                        latency_ms=random.randint(240, 4800),
                        error="TransientProviderError: 529 overloaded" if failed else None,
                        created_at=day,
                        updated_at=day,
                    )
                )

        # Agent runs, mostly successful.
        for index in range(8):
            succeeded = index % 4 != 3
            session.add(
                AgentRun(
                    name="support",
                    model="anthropic:claude-sonnet-5",
                    status=RunStatus.succeeded if succeeded else RunStatus.failed,
                    prompt=random.choice(PROMPTS),
                    output="Order 4021 shipped on Tuesday via DHL." if succeeded else None,
                    error=None if succeeded else "Agent stopped after reaching max_steps=6.",
                    steps=random.randint(2, 6),
                    total_tokens=random.randint(1200, 9000),
                    cost_usd=random.uniform(0.02, 0.35),
                    latency_ms=random.randint(1800, 12000),
                )
            )

        # Jobs in every state, so the queue page has something to act on.
        for name, status, error in [
            ("summarise_conversation", JobStatus.succeeded, None),
            ("summarise_conversation", JobStatus.succeeded, None),
            ("rebuild_search_index", JobStatus.running, None),
            ("send_weekly_digest", JobStatus.queued, None),
            ("transcode_upload", JobStatus.failed, "ValueError: unsupported codec 'av1'"),
            ("export_report", JobStatus.cancelled, None),
        ]:
            finished = status in (JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled)
            session.add(
                Job(
                    name=name,
                    payload={"id": random.randint(1, 50)},
                    status=status,
                    run_at=utcnow(),
                    attempts=3 if status is JobStatus.failed else 1,
                    max_attempts=3,
                    error=error,
                    started_at=utcnow() if status is not JobStatus.queued else None,
                    finished_at=utcnow() if finished else None,
                )
            )

        # Conversations, so the demo's own model has rows in the admin.
        for prompt in PROMPTS:
            session.add(Conversation(prompt=prompt, reply="…", model="anthropic:claude-sonnet-5"))

        for message, action in [
            ("demo created Conversation", AuditAction.create),
            ("demo signed in", AuditAction.login),
            ("demo updated Conversation", AuditAction.update),
            ("demo deleted Conversation", AuditAction.delete),
            ("demo changed their password", AuditAction.update),
        ]:
            session.add(
                AuditLog(action=action, message=message, object_type="Conversation", actor_id=1)
            )

        await session.flush()

        await create_api_key(
            session,
            name="Mobile app",
            scopes=["chat:write", "jobs:read"],
            rate_limit_per_minute=60,
            monthly_budget_usd=50.0,
        )
        await create_api_key(session, name="Internal batch", scopes=["jobs:write"])

    print("Seeded. Now run:  make demo")
    print("Then sign in at http://127.0.0.1:8000/admin as demo / demopassword1")


if __name__ == "__main__":
    asyncio.run(main())
