"""Phase 8 backend hardening behavior tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from app.config import Settings
from app.events.bus import EventBus
from app.models import ReportRun
from app.pipeline.extract import fetch_sources
from app.pipeline.orchestrator import _search_all, run_pipeline
from app.pipeline.search import SearchResult


def make_run(run_id: str, topic: str) -> ReportRun:
    from datetime import UTC, datetime

    return ReportRun(id=run_id, topic=topic, created_at=datetime.now(UTC))


@pytest.mark.asyncio
async def test_search_call_cap_limits_concurrent_planned_queries() -> None:
    @dataclass
    class Provider:
        calls: list[str]

        async def search(self, query: str, max_results: int) -> list[SearchResult]:
            self.calls.append(query)
            await asyncio.sleep(0)
            return []

    provider = Provider([])
    await _search_all(provider, [f"query-{index}" for index in range(20)], max_calls=8)

    assert len(provider.calls) == 8


@pytest.mark.asyncio
async def test_zero_results_is_graceful_and_skips_synthesis(tmp_path) -> None:
    bus = EventBus()
    await bus.register(make_run("zero", "zero results drill"))
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))

    await run_pipeline("zero", bus, settings)

    snapshot = await bus.get_snapshot("zero")
    events = [event async for event in bus.stream("zero")]
    assert snapshot.status == "completed"
    assert snapshot.outcome == "no_results"
    assert snapshot.search_calls <= snapshot.max_search_calls
    assert snapshot.message == "No sources found. Try a different topic."
    assert snapshot.report_md is None
    assert any(event.type == "no_results" for event in events)
    completed = next(event for event in events if event.type == "run_completed")
    assert completed.payload["search_calls"] <= completed.payload["max_search_calls"]
    assert not any(event.type == "report_token" for event in events)


@pytest.mark.asyncio
async def test_dead_source_is_skipped_with_reason_and_run_completes(tmp_path) -> None:
    bus = EventBus()
    await bus.register(make_run("dead", "dead source drill"))
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))

    await run_pipeline("dead", bus, settings)

    snapshot = await bus.get_snapshot("dead")
    events = [event async for event in bus.stream("dead")]
    skipped = [event for event in events if event.type == "source_skipped"]
    assert snapshot.status == "completed"
    assert snapshot.outcome == "no_sources"
    assert skipped
    assert skipped[0].payload["kind"] == "dead"
    assert skipped[0].payload["reason"] == "fixture_content_empty"


@pytest.mark.asyncio
async def test_mock_extraction_reads_pages_without_http(tmp_path) -> None:
    class NeverHttpClient:
        async def get(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("mock extraction attempted network access")

        async def aclose(self) -> None:
            return None

    result = SearchResult(
        title="local page",
        url="https://offline.mock/quantum-computing-2026/algorithms",
        content="not used because the page is file-backed",
    )
    sources = await fetch_sources(
        [result],
        mock_mode=True,
        http_client=NeverHttpClient(),  # type: ignore[arg-type]
    )

    assert len(sources) == 1
    assert "Quantum algorithms" in sources[0].content
    assert sources[0].extraction_method == "mock"


@pytest.mark.asyncio
async def test_partial_synthesis_is_persisted_and_completes(monkeypatch, tmp_path) -> None:
    async def partial_stream(*args: object, **kwargs: object):
        yield "## Partial finding\n\nA claim from the first token [1]."
        raise TimeoutError("synthetic timeout")

    monkeypatch.setattr("app.pipeline.orchestrator.stream_report", partial_stream)
    bus = EventBus()
    await bus.register(make_run("partial", "quantum computing 2026"))
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))

    await run_pipeline("partial", bus, settings)

    snapshot = await bus.get_snapshot("partial")
    events = [event async for event in bus.stream("partial")]
    assert snapshot.status == "completed"
    assert snapshot.partial is True
    assert snapshot.outcome == "partial"
    assert snapshot.report_md is not None
    assert "A claim from the first token" in snapshot.report_md
    assert "Synthesis stopped before completion" in snapshot.report_md
    assert any(event.type == "synthesis_partial" for event in events)
    assert events[-1].type == "run_completed"


@pytest.mark.asyncio
async def test_mock_timeout_drill_is_available_through_the_normal_pipeline(tmp_path) -> None:
    bus = EventBus()
    await bus.register(make_run("partial-drill", "synthesis timeout drill"))
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))

    await run_pipeline("partial-drill", bus, settings)

    snapshot = await bus.get_snapshot("partial-drill")
    assert snapshot.status == "completed"
    assert snapshot.outcome == "partial"
    assert snapshot.partial is True
    assert snapshot.report_md and "Partial report" in snapshot.report_md


@pytest.mark.asyncio
async def test_stage_timing_is_monotonic_and_budgeted(tmp_path) -> None:
    bus = EventBus()
    await bus.register(make_run("timed", "quantum computing 2026"))
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))

    await run_pipeline("timed", bus, settings)

    snapshot = await bus.get_snapshot("timed")
    events = [event async for event in bus.stream("timed")]
    completed = [event for event in events if event.type == "stage_completed"]
    assert snapshot.total_elapsed_ms >= 0
    assert snapshot.budget_status in {"within_budget", "exceeded"}
    assert set(snapshot.stage_timings) >= {"PLANNING", "SEARCHING", "EXTRACTING", "SYNTHESIZING"}
    assert all(event.payload["persisted"] is True for event in completed)
    assert all(event.payload["elapsed_ms"] >= 0 for event in completed)
    assert all(
        event.payload["budget_status"] in {"within_budget", "exceeded"}
        for event in completed
    )
