"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.reports import router as reports_router
from app.config import get_settings
from app.events.bus import EventBus
from app.storage import load_snapshots

app = FastAPI(
    title="One-Click Research Report Agent",
    version="0.1.0",
    description="API foundation for live, citation-backed research reports.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.event_bus = EventBus()
app.state.report_tasks = set()
app.state.settings = get_settings()
for snapshot in load_snapshots(app.state.settings.runs_dir):
    app.state.event_bus.restore(snapshot)

app.include_router(health_router)
app.include_router(reports_router)
