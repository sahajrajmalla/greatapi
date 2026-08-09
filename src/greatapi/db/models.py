"""Framework-owned tables.

All of these are created for every install, including one without the AI extra.
Registering models conditionally would make ``alembic autogenerate`` propose
dropping whatever the current environment cannot see, which is a far worse
failure than two tables that stay empty.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from greatapi.db.base import Base, TimestampMixin, UTCDateTime

__all__ = [
    "APIKey",
    "AgentRun",
    "AuditAction",
    "AuditLog",
    "Job",
    "JobStatus",
    "LLMCall",
    "RunStatus",
    "User",
]


def _enum(enum_type: type[Enum], name: str) -> SQLEnum:
    """Portable enum column: VARCHAR + CHECK constraint.

    Native Postgres enums need a CREATE TYPE migration and cannot be altered in
    place, so a checked string keeps SQLite and Postgres on identical DDL.
    """
    return SQLEnum(enum_type, name=name, native_enum=False, length=32, validate_strings=True)


class User(TimestampMixin, Base):
    __tablename__ = "greatapi_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_number: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    api_keys: Mapped[list[APIKey]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.username!r}>"


class APIKey(TimestampMixin, Base):
    """A machine-to-machine credential with scopes, a rate limit and a budget.

    Only the SHA-256 digest is stored. ``prefix`` exists so the admin can name a
    key in a list without being able to reveal it.
    """

    __tablename__ = "greatapi_api_key"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    hashed_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer)
    monthly_budget_usd: Mapped[float | None] = mapped_column(Float)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("greatapi_user.id", ondelete="CASCADE"), index=True
    )
    user: Mapped[User | None] = relationship(back_populates="api_keys")

    def __repr__(self) -> str:
        return f"<APIKey {self.name!r} prefix={self.prefix!r}>"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class Job(TimestampMixin, Base):
    """A unit of deferred work, durable across restarts."""

    __tablename__ = "greatapi_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus, "job_status"), default=JobStatus.queued, nullable=False, index=True
    )
    result: Mapped[Any | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    run_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    __table_args__ = (Index("ix_greatapi_job_claim", "status", "run_at"),)

    def __repr__(self) -> str:
        return f"<Job {self.name!r} #{self.id} {self.status}>"


class AuditAction(str, Enum):
    create = "create"
    update = "update"
    delete = "delete"
    login = "login"
    logout = "logout"


class AuditLog(TimestampMixin, Base):
    """Who changed what, surfaced on the admin dashboard."""

    __tablename__ = "greatapi_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[AuditAction] = mapped_column(
        _enum(AuditAction, "audit_action"), nullable=False, index=True
    )
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(120), index=True)
    object_id: Mapped[str | None] = mapped_column(String(64))
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("greatapi_user.id", ondelete="SET NULL"), index=True
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.message!r}>"


class RunStatus(str, Enum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class LLMCall(TimestampMixin, Base):
    """One provider request: tokens, cost, latency and outcome.

    Written out-of-band by the provider wrapper on every call, which is what
    turns the admin dashboard into real observability rather than a mockup.
    """

    __tablename__ = "greatapi_llm_call"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    operation: Mapped[str] = mapped_column(String(40), default="complete", nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        _enum(RunStatus, "llm_call_status"), default=RunStatus.succeeded, nullable=False, index=True
    )
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    api_key_id: Mapped[int | None] = mapped_column(
        ForeignKey("greatapi_api_key.id", ondelete="SET NULL"), index=True
    )
    agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("greatapi_agent_run.id", ondelete="CASCADE"), index=True
    )

    __table_args__ = (Index("ix_greatapi_llm_call_model_created", "model", "created_at"),)

    def __repr__(self) -> str:
        return f"<LLMCall {self.model!r} {self.total_tokens}tok ${self.cost_usd:.4f}>"


class AgentRun(TimestampMixin, Base):
    """One agent invocation, with its steps recorded as linked ``LLMCall`` rows."""

    __tablename__ = "greatapi_agent_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        _enum(RunStatus, "agent_run_status"), default=RunStatus.running, nullable=False, index=True
    )
    prompt: Mapped[str | None] = mapped_column(Text)
    output: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    calls: Mapped[list[LLMCall]] = relationship(cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<AgentRun {self.name!r} #{self.id} {self.status}>"
