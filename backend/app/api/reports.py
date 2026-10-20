"""Report creation, snapshots, Markdown, multi-format export, diff, and SSE endpoints."""

from __future__ import annotations

import asyncio
import html
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import markdown as markdown_lib
from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse

from app.models import ReportRun, TopicRequest
from app.pdf.renderer import render_pdf
from app.pipeline.diff import diff_reports
from app.pipeline.orchestrator import run_pipeline
from app.pipeline.renderers import RENDERERS
from app.storage import save_snapshot

router = APIRouter(prefix="/api/reports", tags=["reports"])
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_KIND_MEDIA = {
    "executive": ("text/markdown", "md"),
    "blog": ("text/markdown", "md"),
    "linkedin": ("text/markdown", "md"),
    "marp": ("text/markdown", "md"),
    "slides": ("text/markdown", "md"),
}


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
    task = asyncio.create_task(run_pipeline(run.id, bus, settings, request.app.state.report_tasks))
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


async def _require_ready_report(request: Request, run_id: str) -> ReportRun:
    """Load a snapshot and require an exportable (complete, non-partial) report."""

    try:
        snapshot = await _bus(request).get_snapshot(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report run not found") from exc
    if not _SAFE_RUN_ID.fullmatch(snapshot.id):
        raise HTTPException(status_code=404, detail="Report run not found")
    if not snapshot.report_md:
        raise HTTPException(status_code=409, detail="Report is not ready")
    if snapshot.partial:
        raise HTTPException(status_code=409, detail="Partial reports cannot be exported")
    return snapshot


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


@router.get("/{run_id}/report.html")
async def get_report_html(run_id: str, request: Request) -> Response:
    """Return the report rendered as a standalone HTML document."""

    snapshot = await _require_ready_report(request, run_id)
    body = markdown_lib.markdown(
        html.escape(snapshot.report_md or ""),
        extensions=["tables", "fenced_code"],
        output_format="html5",
    )
    document = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(snapshot.topic)}</title></head><body>{body}</body></html>"
    )
    return Response(content=document, media_type="text/html")


_MD_INLINE = re.compile(r"(\*\*|\*|`)")


def _strip_markdown(report_md: str) -> str:
    """Remove Markdown heading, list, emphasis, and citation markers."""

    lines: list[str] = []
    for line in report_md.splitlines():
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"^\s*[-*]\s+", "", line)
        line = re.sub(r"\[(\d+)\]", "", line)
        line = _MD_INLINE.sub("", line)
        lines.append(line.rstrip())
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


@router.get("/{run_id}/report.txt")
async def get_report_text(run_id: str, request: Request) -> Response:
    """Return the report as Markdown-stripped plain text."""

    snapshot = await _require_ready_report(request, run_id)
    return Response(content=_strip_markdown(snapshot.report_md or ""), media_type="text/plain")


@router.get("/{run_id}/report.json")
async def get_report_json(run_id: str, request: Request) -> Response:
    """Return the report with its citation registry and stage timings as JSON."""

    snapshot = await _require_ready_report(request, run_id)
    payload = {
        "id": snapshot.id,
        "topic": snapshot.topic,
        "created_at": snapshot.created_at.isoformat(),
        "outcome": snapshot.outcome,
        "report_md": snapshot.report_md,
        "sources": [entry.model_dump(mode="json") for entry in snapshot.sources],
        "stage_timings": {
            stage: timing.elapsed_ms for stage, timing in snapshot.stage_timings.items()
        },
        "budget_status": snapshot.budget_status,
        "total_elapsed_ms": snapshot.total_elapsed_ms,
    }
    return Response(
        content=json.dumps(payload, indent=2) + "\n",
        media_type="application/json",
    )


@router.get("/{run_id}/report/{kind}")
async def get_report_kind(run_id: str, kind: str, request: Request) -> Response:
    """Return one derived distribution format from the shared citation registry."""

    renderer = RENDERERS.get(kind)
    if renderer is None:
        raise HTTPException(status_code=404, detail="Unknown report format")
    snapshot = await _require_ready_report(request, run_id)
    media_type, extension = _KIND_MEDIA[kind]
    return Response(
        content=renderer(snapshot.report_md or ""),
        media_type=media_type,
        headers={
            "content-disposition": f'attachment; filename="{snapshot.id}.{extension}"',
        },
    )


@router.get("/{run_id}/diff")
async def get_report_diff(
    run_id: str,
    request: Request,
    compare_run_id: str = Query(min_length=1, max_length=128),
) -> dict[str, object]:
    """Compare this run against an earlier completed run of the same topic."""

    current = await _require_ready_report(request, run_id)
    try:
        previous = await _bus(request).get_snapshot(compare_run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Comparison run not found") from exc
    if not previous.report_md:
        raise HTTPException(status_code=409, detail="Comparison report is not ready")
    if previous.partial or current.partial:
        raise HTTPException(status_code=409, detail="Partial reports cannot be compared")
    return diff_reports(previous, current)


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

    snapshot = await _require_ready_report(request, run_id)
    cache_path = _pdf_cache_path(snapshot, _settings(request).runs_dir)

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
