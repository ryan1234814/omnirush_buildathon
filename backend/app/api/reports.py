"""Report creation, snapshots, Markdown, and SSE endpoints."""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse

from app.models import ReportRun, TopicRequest
from app.pdf.renderer import render_pdf
from app.pipeline.orchestrator import run_pipeline
from app.storage import save_snapshot

router = APIRouter(prefix="/api/reports", tags=["reports"])
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _bus(request: Request):
    """Return the app-scoped event bus."""

    return request.app.state.event_bus


def _settings(request: Request):
    """Return the app-scoped runtime settings."""

    return request.app.state.settings


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_report(payload: TopicRequest, request: Request) -> dict[str, str]:
    """Create a run and start its pipeline in the background."""

    run = ReportRun(
        id=uuid.uuid4().hex,
        topic=payload.topic,
        created_at=datetime.now(UTC),
    )
    bus = _bus(request)
    settings = _settings(request)
    await bus.register(run)
    save_snapshot(run, settings.runs_dir)
    task = asyncio.create_task(run_pipeline(run.id, bus, settings))
    tasks: set[object] = request.app.state.report_tasks
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return {"id": run.id}


@router.get("/{run_id}", response_model=ReportRun)
async def get_report(run_id: str, request: Request) -> ReportRun:
    """Return the latest durable in-memory snapshot."""

    try:
        return await _bus(request).get_snapshot(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report run not found") from exc


@router.get("/{run_id}/report.md")
async def get_report_markdown(run_id: str, request: Request) -> Response:
    """Return the assembled Markdown report once available."""

    try:
        snapshot = await _bus(request).get_snapshot(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report run not found") from exc
    if not snapshot.report_md:
        raise HTTPException(status_code=409, detail="Report is not ready")
    return Response(content=snapshot.report_md, media_type="text/markdown")


def _pdf_cache_path(snapshot: ReportRun, runs_dir: str | Path) -> Path:
    """Return a PDF path only for a safe, snapshot-derived filename."""

    if not _SAFE_RUN_ID.fullmatch(snapshot.id):
        raise ValueError("snapshot id is not safe for a cache filename")
    return Path(runs_dir) / f"{snapshot.id}.pdf"


def _cache_pdf(path: Path, content: bytes) -> None:
    """Write a generated PDF atomically so readers never see a partial artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@router.get("/{run_id}/report.pdf")
async def get_report_pdf(run_id: str, request: Request) -> FileResponse:
    """Return a cached PDF report, generating it after Markdown is available."""

    try:
        snapshot = await _bus(request).get_snapshot(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report run not found") from exc
    if not snapshot.report_md:
        raise HTTPException(status_code=409, detail="Report is not ready")
    if snapshot.partial:
        raise HTTPException(status_code=409, detail="Partial reports cannot be exported")

    try:
        cache_path = _pdf_cache_path(snapshot, _settings(request).runs_dir)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Report run not found") from exc

    if not cache_path.is_file():
        _cache_pdf(cache_path, render_pdf(snapshot.report_md))
    return FileResponse(
        cache_path,
        media_type="application/pdf",
        filename=f"{snapshot.id}.pdf",
    )


@router.get("/{run_id}/events")
async def report_events(
    run_id: str,
    request: Request,
    last_event_id_header: str | None = Header(default=None, alias="Last-Event-ID"),
    last_event_id_query: str | None = Query(default=None, alias="last_event_id"),
) -> StreamingResponse:
    """Stream replayable Server-Sent Events until the run reaches a terminal state."""

    bus = _bus(request)
    try:
        await bus.get_snapshot(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report run not found") from exc
    try:
        replay_from = max(0, int(last_event_id_header or last_event_id_query or "0"))
    except ValueError:
        replay_from = 0

    async def event_stream():
        async for event in bus.stream(run_id, replay_from):
            payload = json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
            yield f"id: {event.seq}\nevent: {event.type}\ndata: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
