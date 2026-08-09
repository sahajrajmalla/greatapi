"""Template rendering plus the context every admin page needs."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any
from urllib.parse import urlencode

from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from greatapi.admin.registry import get_registry
from greatapi.conf.settings import ADMIN_TEMPLATE_DIR, get_settings
from greatapi.db.models import User
from greatapi.security.csrf import CSRF_FIELD_NAME
from greatapi.security.sessions import read_session

__all__ = ["FLASH_MESSAGES", "Page", "flash_url", "paginate", "render", "templates"]

templates = Jinja2Templates(directory=str(ADMIN_TEMPLATE_DIR))
templates.env.trim_blocks = True
templates.env.lstrip_blocks = True

#: Flash messages are looked up by code rather than passed through the query
#: string, so a crafted URL cannot put arbitrary text on an admin page.
FLASH_MESSAGES: dict[str, tuple[str, str]] = {
    "saved": ("success", "Changes saved."),
    "created": ("success", "Created successfully."),
    "deleted": ("success", "Deleted successfully."),
    "password-changed": ("success", "Password updated."),
    "key-revoked": ("success", "API key revoked."),
    "job-retried": ("success", "Job queued for another attempt."),
    "logged-out": ("info", "You have been signed out."),
    "not-found": ("error", "That record no longer exists."),
    "forbidden": ("error", "You are not allowed to do that."),
    "invalid": ("error", "Please correct the errors below."),
}


def flash_url(path: str, code: str, **params: Any) -> str:
    query = urlencode({"flash": code, **{k: v for k, v in params.items() if v is not None}})
    return f"{path}?{query}"


@dataclass(slots=True)
class Page:
    """One page of results, plus what a pager needs to render itself."""

    items: list[Any]
    total: int
    number: int
    size: int

    @property
    def pages(self) -> int:
        return max(1, ceil(self.total / self.size)) if self.size else 1

    @property
    def has_previous(self) -> bool:
        return self.number > 1

    @property
    def has_next(self) -> bool:
        return self.number < self.pages

    @property
    def start_index(self) -> int:
        return 0 if not self.total else (self.number - 1) * self.size + 1

    @property
    def end_index(self) -> int:
        return min(self.number * self.size, self.total)


def paginate(items: list[Any], total: int, number: int, size: int) -> Page:
    return Page(items=items, total=total, number=number, size=size)


def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    *,
    user: User | None = None,
    active: str = "",
    status_code: int = 200,
) -> Response:
    """Render an admin template with the shared shell context."""
    settings = get_settings()
    session = read_session(request)
    flash_code = request.query_params.get("flash")
    flash = FLASH_MESSAGES.get(flash_code) if flash_code else None

    base: dict[str, Any] = {
        "settings": settings,
        "admin_path": settings.admin_path,
        "static_path": f"{settings.admin_path}/_static",
        "site_title": settings.admin_title,
        "current_user": user,
        "active": active,
        "groups": get_registry().by_group(),
        "ai_enabled": settings.ai_enabled,
        "flash_level": flash[0] if flash else None,
        "flash_message": flash[1] if flash else None,
        "csrf_token": session.csrf_token if session else "",
        "csrf_field": CSRF_FIELD_NAME,
    }
    base.update(context or {})
    return templates.TemplateResponse(request, template, base, status_code=status_code)
