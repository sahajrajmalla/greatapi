"""The :class:`GreatAPI` application class."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from greatapi import __version__
from greatapi.apps import load_apps
from greatapi.conf.settings import ADMIN_STATIC_DIR, Settings, get_settings
from greatapi.db.session import create_all, dispose_engine, get_engine
from greatapi.jobs.router import jobs_router
from greatapi.jobs.worker import Worker
from greatapi.security.dependencies import NotAuthenticated

__all__ = ["GreatAPI"]

logger = logging.getLogger("greatapi")

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
}

# Every admin asset is served from this origin, so the policy can be strict with
# no escape hatches: no CDN, no inline script, no inline style.
_ADMIN_CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
    "form-action 'self'"
)


class GreatAPI(FastAPI):
    """A :class:`~fastapi.FastAPI` application with the batteries wired in.

    ::

        from greatapi import GreatAPI

        app = GreatAPI(title="My Backend", installed_apps=["blog"])

    On top of FastAPI this adds the admin site, the job worker, job status
    endpoints, security headers and managed database lifecycle. Everything is
    opt-out: pass ``admin=False`` or ``jobs=False`` to leave a piece behind.

    ``installed_apps`` wires each app by convention -- its models, its admin
    registrations and its router -- so ``greatapi startapp`` produces something
    that runs instead of something you then have to hand-register.
    """

    def __init__(
        self,
        *,
        title: str | None = None,
        version: str = "0.1.0",
        installed_apps: list[str] | None = None,
        admin: bool | None = None,
        jobs: bool | None = None,
        create_tables: bool | None = None,
        settings: Settings | None = None,
        lifespan: Callable[[FastAPI], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self.settings = settings or get_settings()
        self.installed_apps = list(installed_apps or [])
        self.enable_admin = self.settings.admin_enabled if admin is None else admin
        self.enable_jobs = self.settings.jobs_enabled if jobs is None else jobs
        # Creating tables on boot is a development convenience. With debug off,
        # schema changes must go through `greatapi migrate` so they are versioned.
        self.create_tables = self.settings.debug if create_tables is None else create_tables
        self.worker: Worker | None = None
        self._user_lifespan = lifespan

        super().__init__(
            title=title or self.settings.admin_title,
            version=version,
            debug=self.settings.debug,
            lifespan=self._lifespan,
            **kwargs,
        )

        self.middleware("http")(self._security_headers)
        self.add_exception_handler(NotAuthenticated, self._handle_not_authenticated)

        # Apps first: their models must be imported and their admin classes
        # registered before the admin router enumerates the registry.
        load_apps(self.installed_apps, self)

        if self.enable_admin:
            self._mount_admin()
        self.include_router(jobs_router)

    # -- lifecycle --------------------------------------------------------

    @asynccontextmanager
    async def _lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        get_engine()
        if self.create_tables:
            await create_all()

        if self.enable_jobs:
            self.worker = Worker()
            self.worker.start()

        logger.info("GreatAPI %s ready", __version__)
        try:
            async with AsyncExitStack() as stack:
                if self._user_lifespan is not None:
                    await stack.enter_async_context(self._user_lifespan(app))
                yield
        finally:
            if self.worker is not None:
                await self.worker.stop()
                self.worker = None
            await dispose_engine()

    # -- wiring -----------------------------------------------------------

    def _mount_admin(self) -> None:
        from greatapi.admin.router import build_admin_router

        # Mounted before the router so `/_static/...` is never swallowed by the
        # `/{app_label}/{model}` catch-all below it.
        self.mount(
            f"{self.settings.admin_path}/_static",
            StaticFiles(directory=ADMIN_STATIC_DIR),
            name="greatapi-static",
        )
        self.include_router(build_admin_router())

    # -- cross-cutting behaviour -----------------------------------------

    async def _security_headers(
        self, request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        response: Response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if request.url.path.startswith(self.settings.admin_path):
            response.headers.setdefault("Content-Security-Policy", _ADMIN_CSP)
        return response

    def _handle_not_authenticated(self, request: Request, exc: Exception) -> Response:
        """Redirect browsers to the login page; leave API clients a clean 401."""
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            target = f"{self.settings.admin_path}/login"
            if request.url.path != target:
                target = f"{target}?next={request.url.path}"
            return RedirectResponse(target, status_code=303)
        return JSONResponse({"detail": "Not authenticated."}, status_code=401)
