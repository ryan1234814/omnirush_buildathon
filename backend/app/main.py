"""FastAPI application entry point."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.health import router as health_router
from app.api.notifications import router as notifications_router
from app.api.refinement import router as refinement_router
from app.api.reports import router as reports_router
from app.api.schedules import router as schedules_router
from app.config import get_settings
from app.events.bus import EventBus
from app.scheduler import SchedulerService
from app.storage import load_snapshots

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run the recurring-report scheduler loop for the lifetime of the app."""

    async def scheduler_loop() -> None:
        tick_seconds = app.state.settings.scheduler_tick_seconds
        while True:
            await asyncio.sleep(tick_seconds)
            try:
                await app.state.scheduler.tick()
            except Exception:
                logger.exception("Scheduler tick failed")

    loop_task = asyncio.create_task(scheduler_loop())
    try:
        yield
    finally:
        loop_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await loop_task


app = FastAPI(
    title="One-Click Research Report Agent",
    version="0.1.0",
    description="API foundation for live, citation-backed research reports.",
    lifespan=lifespan,
)

app.state.settings = settings = get_settings()

# The API is public and cookie-less, so credentials are only enabled when the operator has
# pinned explicit origins. A wildcard origin must NOT be paired with credentials (browsers
# reject `Access-Control-Allow-Origin: *` with `Allow-Credentials: true`), so it is disabled.
cors_origins = settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.event_bus = EventBus()
app.state.report_tasks = set()
app.state.follow_up_conversations = {}
app.state.scheduler = SchedulerService(
    app.state.settings, app.state.event_bus, app.state.report_tasks
)
for snapshot in load_snapshots(app.state.settings.runs_dir):
    app.state.event_bus.restore(snapshot)

app.include_router(health_router)
app.include_router(reports_router)
app.include_router(refinement_router)
app.include_router(schedules_router)
app.include_router(notifications_router)

# The container copies the built UI to /app/frontend-dist; locally STATIC_DIR opts the
# API into serving a production build. Routers are registered above, so /api/* keeps priority.
if app.state.settings.static_dir:
    app.mount("/", StaticFiles(directory=app.state.settings.static_dir, html=True), name="static")
