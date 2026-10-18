"""End-to-end mock API and SSE checkpoint."""

import asyncio

import httpx
import pytest

from app.config import Settings
from app.events.bus import EventBus
from app.main import app


@pytest.mark.asyncio
async def test_mock_report_api_completes_and_replays_sse(tmp_path) -> None:
    original_bus = app.state.event_bus
    original_settings = app.state.settings
    original_tasks = app.state.report_tasks
    app.state.event_bus = EventBus()
    app.state.settings = Settings(
        mock_mode=True,
        search_provider="mock",
        runs_dir=str(tmp_path),
        top_k=6,
    )
    app.state.report_tasks = set()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/reports", json={"topic": "quantum computing"})
            assert response.status_code == 202
            run_id = response.json()["id"]

            event_response = await client.get(f"/api/reports/{run_id}/events")
            assert event_response.status_code == 200
            assert "event: stage_started" in event_response.text
            assert "event: source_fetched" in event_response.text
            assert "event: run_completed" in event_response.text

            snapshot = await client.get(f"/api/reports/{run_id}")
            assert snapshot.json()["status"] == "completed"
            report = await client.get(f"/api/reports/{run_id}/report.md")
            assert report.status_code == 200
            assert "## Sources" in report.text
            assert "[1]" in report.text

            replay = await client.get(
                f"/api/reports/{run_id}/events",
                headers={"Last-Event-ID": "0"},
            )
            assert replay.status_code == 200
            assert "event: run_completed" in replay.text

            query_replay = await client.get(f"/api/reports/{run_id}/events?last_event_id=0")
            assert query_replay.status_code == 200
            assert "event: run_completed" in query_replay.text
    finally:
        for task in list(app.state.report_tasks):
            if not task.done():
                task.cancel()
        await asyncio.gather(*app.state.report_tasks, return_exceptions=True)
        app.state.event_bus = original_bus
        app.state.settings = original_settings
        app.state.report_tasks = original_tasks
