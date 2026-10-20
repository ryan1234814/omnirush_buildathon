"""Follow-up refinement chat against completed reports."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.config import Settings
from app.events.bus import EventBus
from app.main import app
from app.models import ReportRun, SourceEntry


def _completed_run(run_id: str, status: str = "completed") -> ReportRun:
    return ReportRun(
        id=run_id,
        topic="quantum computing 2026",
        created_at=datetime.now(UTC),
        status=status,
        stage="DONE" if status == "completed" else "SYNTHESIZING",
        outcome="completed" if status == "completed" else "pending",
        report_md="# Research report\n\n## Executive summary\n\nDone [1].\n",
        sources=[
            SourceEntry(id=1, url="https://one.test", title="One", excerpt="Evidence one."),
            SourceEntry(id=2, url="https://two.test", title="Two", excerpt="Evidence two."),
        ],
    )


async def _client_for(monkeypatch, tmp_path, runs: list[ReportRun], settings: Settings):
    bus = EventBus()
    for run in runs:
        await bus.register(run)
    monkeypatch.setattr(app.state, "event_bus", bus)
    monkeypatch.setattr(app.state, "settings", settings)
    monkeypatch.setattr(app.state, "report_tasks", set())
    monkeypatch.setattr(app.state, "follow_up_conversations", {})
    return TestClient(app)


async def test_chat_returns_grounded_answer_with_citations(monkeypatch, tmp_path) -> None:
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))
    client = await _client_for(
        monkeypatch, tmp_path, [_completed_run("done-run")], settings
    )

    response = client.post(
        "/api/reports/done-run/chat",
        json={"message": "What changed since last year?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert body["citations"] == [1]
    assert body["conversation_id"]

    follow_up = client.post(
        "/api/reports/done-run/chat",
        json={"message": "Go deeper", "conversation_id": body["conversation_id"]},
    )
    assert follow_up.status_code == 200
    history = app.state.follow_up_conversations[body["conversation_id"]]
    assert len(history) == 4


async def test_chat_accepts_legacy_prompt_field(monkeypatch, tmp_path) -> None:
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))
    client = await _client_for(
        monkeypatch, tmp_path, [_completed_run("legacy-run")], settings
    )

    response = client.post("/api/reports/legacy-run/chat", json={"prompt": "Summarize section 1"})

    assert response.status_code == 200


async def test_chat_rejects_unknown_and_incomplete_runs(monkeypatch, tmp_path) -> None:
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))
    running = _completed_run("running-run", status="running")
    running.report_md = None
    client = await _client_for(monkeypatch, tmp_path, [running], settings)

    missing = client.post("/api/reports/does-not-exist/chat", json={"message": "hello"})
    assert missing.status_code == 404
    incomplete = client.post("/api/reports/running-run/chat", json={"message": "hello"})
    assert incomplete.status_code == 409


async def test_real_mode_without_llm_key_is_unavailable(monkeypatch, tmp_path) -> None:
    settings = Settings(mock_mode=False, openai_api_key=None, runs_dir=str(tmp_path))
    client = await _client_for(monkeypatch, tmp_path, [_completed_run("no-llm")], settings)

    response = client.post("/api/reports/no-llm/chat", json={"message": "hello"})

    assert response.status_code == 503
