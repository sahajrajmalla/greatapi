"""Admin configuration for the framework's own tables.

Note what is *not* here: ``hashed_password`` on :class:`~greatapi.db.User` and
``hashed_key`` on :class:`~greatapi.db.APIKey` appear in no ``list_display`` and
no ``fields``. Even if they did, the registry redacts them -- these declarations
are the first of two independent defences, not the only one.
"""

from __future__ import annotations

from greatapi.admin.registry import ModelAdmin, register
from greatapi.db.models import AgentRun, APIKey, AuditLog, Job, LLMCall, User

__all__ = ["register_builtin_admins"]

_registered = False


def register_builtin_admins() -> None:
    """Register the framework models. Idempotent."""
    global _registered
    if _registered:
        return
    _registered = True

    @register(User)
    class UserAdmin(ModelAdmin):
        app_label = "auth"
        list_display = (
            "id",
            "username",
            "email",
            "full_name",
            "is_admin",
            "is_active",
            "last_login_at",
        )
        search_fields = ("username", "email", "full_name")
        fields = ("username", "email", "full_name", "contact_number", "is_active", "is_admin")
        readonly_fields = ("created_at", "updated_at", "last_login_at")
        ordering = "-created_at"
        # A user needs a password, and a password is never a writable form
        # field. Accounts come from `greatapi createsuperuser` or your own
        # sign-up flow; the admin edits them and can reset a password.
        can_create = False

    @register(APIKey)
    class APIKeyAdmin(ModelAdmin):
        app_label = "auth"
        list_display = (
            "id",
            "name",
            "prefix",
            "is_active",
            "rate_limit_per_minute",
            "last_used_at",
        )
        search_fields = ("name", "prefix")
        fields = ("name", "is_active", "rate_limit_per_minute", "monthly_budget_usd", "expires_at")
        readonly_fields = ("prefix", "created_at", "last_used_at")
        can_create = False  # Created through the API keys page, which shows the secret once.
        ordering = "-created_at"

    @register(Job)
    class JobAdmin(ModelAdmin):
        app_label = "system"
        list_display = ("id", "name", "status", "attempts", "run_at", "finished_at")
        search_fields = ("name",)
        readonly_fields = ("created_at", "started_at", "finished_at")
        can_create = False
        can_edit = False
        ordering = "-created_at"

    @register(AuditLog)
    class AuditLogAdmin(ModelAdmin):
        app_label = "system"
        list_display = ("id", "action", "message", "object_type", "created_at")
        search_fields = ("message", "object_type")
        can_create = False
        can_edit = False
        ordering = "-created_at"

    @register(LLMCall)
    class LLMCallAdmin(ModelAdmin):
        app_label = "ai"
        list_display = (
            "id",
            "provider",
            "model",
            "status",
            "total_tokens",
            "cost_usd",
            "latency_ms",
            "created_at",
        )
        search_fields = ("model", "provider")
        can_create = False
        can_edit = False
        ordering = "-created_at"

    @register(AgentRun)
    class AgentRunAdmin(ModelAdmin):
        app_label = "ai"
        list_display = ("id", "name", "model", "status", "steps", "total_tokens", "cost_usd")
        search_fields = ("name", "model")
        can_create = False
        can_edit = False
        ordering = "-created_at"
