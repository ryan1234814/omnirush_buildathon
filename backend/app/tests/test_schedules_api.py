"""Schedule CRUD endpoints and recurring-run frequency behavior."""

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.config import Settings
from app.events.bus import EventBus
from app.main import app
from app.models import ReportRun, ScheduleCreate
from app.scheduler import SchedulerService, next_run_at


def _client(monkeypatch, tmp_path) -> TestClient:
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))
    bus = EventBus()
    tasks: set[object] = set()
    monkeypatch.setattr(app.state, "settings", settings)
    monkeypatch.setattr(app.state, "event_bus", bus)
    monkeypatch.setattr(app.state, "report_tasks", tasks)
    monkeypatch.setattr(app.state, "scheduler", SchedulerService(settings, bus, tasks))
    return TestClient(app)


def test_schedule_crud_flow(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    created = client.post(
        "/api/schedules", json={"topic": "quantum computing 2026", "frequency": "weekly"}
    )
    assert created.status_code == 201
    schedule = created.json()
    assert schedule["topic"] == "quantum computing 2026"
    assert schedule["frequency"] == "weekly"
    assert schedule["enabled"] is True
    assert schedule["next_run_at"]

    listed = client.get("/api/schedules")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [schedule["id"]]

    removed = client.delete(f"/api/schedules/{schedule['id']}")
    assert removed.status_code == 204
    assert client.get("/api/schedules").json() == []

    assert client.delete("/api/schedules/missing").status_code == 404


def test_schedule_validation_rejects_bad_payloads(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    assert client.post("/api/schedules", json={"topic": "x"}).status_code == 422
    assert (
        client.post(
            "/api/schedules", json={"topic": "x", "frequency": "weekly", "cron": "0 * * * *"}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/schedules", json={"topic": "x", "frequency": "fortnightly"}).status_code
        == 422
    )
    assert (
        client.post("/api/schedules", json={"topic": " ", "frequency": "daily"}).status_code == 422
    )


def test_next_run_at_supports_once_and_monthly() -> None:
    now = datetime(2026, 1, 31, 12, 0, tzinfo=UTC)

    assert next_run_at(None, "once", now) == now + timedelta(minutes=1)
    assert next_run_at(None, "monthly", now) == datetime(2026, 2, 28, 12, 0, tzinfo=UTC)
    assert next_run_at(None, "weekly", now) == now + timedelta(days=7)


async def test_once_schedule_disables_after_it_runs(monkeypatch, tmp_path) -> None:
    started: list[str] = []

    async def fake_pipeline(run_id: str, bus, settings, tasks=None):
        started.append(run_id)

    monkeypatch.setattr("app.scheduler.run_pipeline", fake_pipeline)
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))
    service = SchedulerService(settings, EventBus(), set())
    service.create(
        ScheduleCreate(topic="quantum computing", frequency="once"),
        now=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )

    first = await service.tick(now=datetime(2026, 1, 1, 12, 2, tzinfo=UTC))
    await asyncio.gather(*list(service.tasks))
    second = await service.tick(now=datetime(2026, 1, 1, 12, 5, tzinfo=UTC))

    assert first == started
    assert second == []
    persisted = service.list()[0]
    assert persisted.enabled is False
    assert persisted.last_run_id == first[0]


async def test_tick_creates_run_linked_to_schedule(monkeypatch, tmp_path) -> None:
    captured: list[ReportRun] = []

    async def fake_pipeline(run_id: str, bus, settings, tasks=None):
        captured.append(await bus.get_snapshot(run_id))

    monkeypatch.setattr("app.scheduler.run_pipeline", fake_pipeline)
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))
    service = SchedulerService(settings, EventBus(), set())
    schedule = service.create(
        ScheduleCreate(topic="quantum computing", frequency="daily"),
        now=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )

    # A daily schedule created at 12:00 is next due 24h later, so tick after that cursor.
    started = await service.tick(now=datetime(2026, 1, 2, 12, 0, tzinfo=UTC))
    await asyncio.gather(*list(service.tasks))

    assert len(started) == 1
    assert captured[0].schedule_id == schedule.id
    after = service.list()[0]
    assert after.next_run_at > datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
