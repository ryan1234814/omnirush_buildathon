"""Self-evaluation and a second research round after gaps are detected."""

from datetime import UTC, datetime

from app.config import Settings
from app.events.bus import EventBus
from app.models import ReportRun
from app.pipeline import orchestrator
from app.pipeline.extract import Source
from app.pipeline.search import SearchResult


class AlternatingProvider:
    """Return one brand-new URL beginning with the second search pass."""

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        self.calls += 1
        results = [
            SearchResult(
                title="First pass",
                url="https://round1.test/a",
                content="Evidence collected during the first research pass.",
                score=0.9,
            )
        ]
        if self.calls > 1:
            results.append(
                SearchResult(
                    title="Second pass",
                    url="https://round2.test/b",
                    content="Evidence collected during the gap-driven second research pass.",
                    score=0.8,
                )
            )
        return results[:max_results]


async def test_second_round_fills_detected_gaps(monkeypatch, tmp_path) -> None:
    provider = AlternatingProvider()

    def fake_provider(settings: Settings, call_budget=None):
        return provider, None

    async def fake_fetch(results, **kwargs):
        return [
            Source(
                title=result.title,
                url=result.url,
                content=result.content * 10,
                search_relevance=result.score,
            )
            for result in results
        ]

    monkeypatch.setattr(orchestrator, "_provider", fake_provider)
    monkeypatch.setattr(orchestrator, "fetch_sources", fake_fetch)

    bus = EventBus()
    await bus.register(ReportRun(id="gap", topic="gap drill", created_at=datetime.now(UTC)))
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))

    await orchestrator.run_pipeline("gap", bus, settings)

    snapshot = await bus.get_snapshot("gap")
    events = [event async for event in bus.stream("gap")]
    event_types = [event.type for event in events]
    assert snapshot.status == "completed"
    assert snapshot.gap_reasons
    assert snapshot.research_rounds == 1
    assert "self_evaluated" in event_types
    assert "research_round_started" in event_types
    assert "research_round_completed" in event_types
    assert provider.calls >= 2
    assert any(
        event.type == "source_fetched" and event.payload.get("round") == 2 for event in events
    )
    assert len(snapshot.sources) >= 2


async def test_no_gap_reasons_skips_the_second_round(monkeypatch, tmp_path) -> None:
    provider = AlternatingProvider()

    def fake_provider(settings: Settings, call_budget=None):
        return provider, None

    async def fake_fetch(results, **kwargs):
        return [
            Source(
                title=result.title,
                url=result.url,
                content=result.content * 10,
                search_relevance=result.score,
            )
            for result in results
        ]

    monkeypatch.setattr(orchestrator, "_provider", fake_provider)
    monkeypatch.setattr(orchestrator, "fetch_sources", fake_fetch)

    bus = EventBus()
    await bus.register(
        ReportRun(id="clean", topic="quantum computing", created_at=datetime.now(UTC))
    )
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))

    await orchestrator.run_pipeline("clean", bus, settings)

    snapshot = await bus.get_snapshot("clean")
    events = [event async for event in bus.stream("clean")]
    assert snapshot.status == "completed"
    assert snapshot.gap_reasons == []
    assert snapshot.research_rounds == 0
    assert "research_round_started" not in [event.type for event in events]
