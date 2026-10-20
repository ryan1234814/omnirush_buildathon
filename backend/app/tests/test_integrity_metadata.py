"""Citation-integrity and cost telemetry surfaced on snapshots and report_evaluated."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.config import Settings
from app.events.bus import EventBus
from app.main import app
from app.models import ReportRun
from app.pipeline.citations import SourceRegistry, count_citations, validate_report
from app.pipeline.orchestrator import run_pipeline


def make_run(run_id: str, topic: str) -> ReportRun:
    return ReportRun(id=run_id, topic=topic, created_at=datetime.now(UTC))


async def test_mock_run_publishes_integrity_and_cost_metadata(tmp_path) -> None:
    bus = EventBus()
    await bus.register(make_run("integrity", "quantum computing 2026"))
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))

    await run_pipeline("integrity", bus, settings)

    snapshot = await bus.get_snapshot("integrity")
    events = [event async for event in bus.stream("integrity")]
    evaluated = next(event for event in events if event.type == "report_evaluated")
    assert events[-1].type == "run_completed"
    assert snapshot.citations_valid > 0
    assert snapshot.citations_removed == 0
    assert snapshot.output_token_estimate > 0
    assert evaluated.payload["citations_valid"] == snapshot.citations_valid
    assert evaluated.payload["citations_removed"] == snapshot.citations_removed
    assert evaluated.payload["context_token_estimate"] >= 0
    assert evaluated.payload["output_token_estimate"] == snapshot.output_token_estimate
    assert evaluated.payload["search_calls"] <= evaluated.payload["max_search_calls"]
    assert evaluated.payload["budget_status"] in {"within_budget", "exceeded"}
    assert evaluated.payload["mock_mode"] is True


async def test_fabricated_citation_is_counted_as_removed(monkeypatch, tmp_path) -> None:
    async def hallucinating_stream(*args: object, **kwargs: object):
        yield "## Fabricated finding\n\nA supported claim [1] and an invented claim [9]."

    monkeypatch.setattr("app.pipeline.orchestrator.stream_report", hallucinating_stream)
    bus = EventBus()
    await bus.register(make_run("fabricated", "quantum computing 2026"))
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))

    await run_pipeline("fabricated", bus, settings)

    snapshot = await bus.get_snapshot("fabricated")
    events = [event async for event in bus.stream("fabricated")]
    assert snapshot.citations_removed == 1
    assert snapshot.citations_valid >= 1
    assert "[9]" not in snapshot.report_md
    assert any(event.type == "citations_removed" for event in events)
    evaluated = next(event for event in events if event.type == "report_evaluated")
    assert evaluated.payload["citations_removed"] == 1


def test_count_citations_handles_both_bracket_styles() -> None:
    assert count_citations("claims [1] and 【2】 plus a plan [3x]") == 2


def test_validate_report_strips_only_invalid_ids() -> None:
    registry = SourceRegistry.model_validate(
        {"entries": [{"id": 1, "url": "https://a.test", "title": "A", "excerpt": "x"}]}
    )
    clean, removed = validate_report("valid [1] and fabricated [7].", registry)
    assert removed == [7]
    assert clean == "valid [1] and fabricated ."


def test_snapshot_endpoints_carry_integrity_fields() -> None:
    run = ReportRun(
        id="artifact-check",
        topic="quantum computing 2026",
        created_at=datetime.now(UTC),
        status="completed",
        report_md="# Report\n\nA cited claim [1].\n\n## Sources\n\n**[1] A** — [u](u)",
        citations_valid=1,
        citations_removed=0,
        output_token_estimate=42,
        search_calls=2,
        max_search_calls=8,
    )
    app.state.event_bus.restore(run)
    client = TestClient(app)

    snapshot_response = client.get("/api/reports/artifact-check")
    assert snapshot_response.status_code == 200
    snapshot_payload = snapshot_response.json()
    assert snapshot_payload["citations_valid"] == 1
    assert snapshot_payload["citations_removed"] == 0
    assert snapshot_payload["output_token_estimate"] == 42

    json_response = client.get("/api/reports/artifact-check/report.json")
    assert json_response.status_code == 200
    artifact = json_response.json()
    assert artifact["citations_valid"] == 1
    assert artifact["citations_removed"] == 0
    assert artifact["output_token_estimate"] == 42
    assert artifact["context_token_estimate"] >= 0
    assert artifact["search_calls"] == 2
