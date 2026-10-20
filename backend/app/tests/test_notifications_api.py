"""In-app notification storage and endpoints."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.config import Settings
from app.events.bus import EventBus
from app.main import app
from app.models import ReportRun
from app.notifications import record_run_notification
from app.pipeline import orchestrator
from app.pipeline.search import SearchResult
from app.storage import load_notifications


async def test_completion_records_an_in_app_notification(monkeypatch, tmp_path) -> None:
    class SingleUrlProvider:
        async def search(self, query: str, max_results: int) -> list[SearchResult]:
            return [
                SearchResult(
                    title="Only source",
                    url="https://only.test/a",
                    content="Deterministic evidence for the notification test.",
                    score=0.9,
                )
            ][:max_results]

    async def fake_fetch(results, **kwargs):
        from app.pipeline.extract import Source

        return [
            Source(title=r.title, url=r.url, content=r.content * 10, search_relevance=r.score)
            for r in results
        ]

    def fake_provider(settings: Settings, call_budget=None):
        return SingleUrlProvider(), None

    monkeypatch.setattr(orchestrator, "_provider", fake_provider)
    monkeypatch.setattr(orchestrator, "fetch_sources", fake_fetch)

    bus = EventBus()
    await bus.register(
        ReportRun(id="notify-me", topic="quantum computing", created_at=datetime.now(UTC))
    )
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))
    await orchestrator.run_pipeline("notify-me", bus, settings)

    notifications = load_notifications(settings.runs_dir)
    assert len(notifications) == 1
    assert notifications[0].run_id == "notify-me"
    assert notifications[0].type == "run_completed"
    assert notifications[0].title == "Report ready: quantum computing"
    assert notifications[0].read is False

    # Re-running the same report replaces rather than duplicates the record.
    record_run_notification(await bus.get_snapshot("notify-me"), settings)
    assert len(load_notifications(settings.runs_dir)) == 1


def test_notification_endpoints(monkeypatch, tmp_path) -> None:
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))
    monkeypatch.setattr(app.state, "settings", settings)
    monkeypatch.setattr(app.state, "event_bus", EventBus())
    record_run_notification(
        ReportRun(
            id="notify-read",
            topic="quantum computing",
            created_at=datetime.now(UTC),
            status="completed",
            outcome="completed",
        ),
        settings,
    )
    record_run_notification(
        ReportRun(
            id="notify-failed",
            topic="broken topic",
            created_at=datetime.now(UTC),
            status="failed",
            error="Pipeline failed during PLANNING: RuntimeError",
        ),
        settings,
    )
    client = TestClient(app)

    listed = client.get("/api/notifications")
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 2
    assert items[0]["run_id"] == "notify-failed"  # newest first
    assert items[0]["type"] == "run_failed"
    assert all(item["read"] is False for item in items)

    target = next(item for item in items if item["run_id"] == "notify-read")
    patched = client.patch(f"/api/notifications/{target['id']}", json={"read": True})
    assert patched.status_code == 200
    assert patched.json()["read"] is True

    unread = client.get("/api/notifications?unread=true").json()
    assert [item["run_id"] for item in unread] == ["notify-failed"]

    assert client.patch("/api/notifications/missing", json={"read": True}).status_code == 404
