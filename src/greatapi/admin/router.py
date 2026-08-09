"""Admin router assembly.

Two things matter about the ordering here:

* every view except login/logout sits behind a router-level ``require_admin``
  dependency, so a newly added view is protected by default rather than by
  remembering to protect it;
* model CRUD lives under ``/model/{group}/{slug}`` instead of ``/{group}/{slug}``,
  so a user model called "usage" or "jobs" can never shadow a built-in page.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from greatapi.admin.builtins import register_builtin_admins
from greatapi.admin.views.account import account_router
from greatapi.admin.views.auth import auth_router
from greatapi.admin.views.dashboard import dashboard
from greatapi.admin.views.jobs import jobs_admin_router
from greatapi.admin.views.keys import keys_router
from greatapi.admin.views.models import models_router
from greatapi.admin.views.usage import usage_router
from greatapi.conf.settings import get_settings
from greatapi.security.csrf import verify_csrf
from greatapi.security.dependencies import require_admin

__all__ = ["build_admin_router"]


def build_admin_router() -> APIRouter:
    settings = get_settings()
    register_builtin_admins()

    root = APIRouter(prefix=settings.admin_path, tags=["Admin"], include_in_schema=False)
    root.include_router(auth_router)

    # Applied per include rather than by nesting a dependency-carrying router:
    # the dashboard lives at the admin root, and a router with both an empty
    # prefix and an empty path is rejected by FastAPI.
    guarded = [Depends(require_admin), Depends(verify_csrf)]
    root.add_api_route(
        "",
        dashboard,
        methods=["GET"],
        dependencies=guarded,
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    root.include_router(account_router, dependencies=guarded)
    root.include_router(jobs_admin_router, dependencies=guarded)
    root.include_router(keys_router, dependencies=guarded)
    if settings.ai_enabled:
        root.include_router(usage_router, dependencies=guarded)
    root.include_router(models_router, dependencies=guarded)

    return root
