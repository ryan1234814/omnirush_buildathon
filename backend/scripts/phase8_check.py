"""Run the deterministic Phase 8 acceptance and resilience drills offline."""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import Settings
from app.events.bus import EventBus
from app.models import ReportRun
from app.pipeline import extract
from app.pipeline.orchestrator import run_pipeline


class NetworkGuardClient:
    """Fail loudly if an offline mock run tries to make an HTTP request."""

    async def get(self, *_args: object, **_kwargs: object) -> Any:
        raise AssertionError("offline mock run attempted an HTTP request")

    async def aclose(self) -> None:
        return None


async def run_case(
    topic: str,
    runs_dir: Path,
    *,
    guard_network: bool = False,
) -> tuple[ReportRun, list[str]]:
    """Run one pipeline case and return its snapshot plus event types."""

    bus = EventBus()
    run = ReportRun(
        id=f"phase8-{topic.replace(' ', '-')}",
        topic=topic,
        created_at=datetime.now(UTC),
    )
    await bus.register(run)
    settings = Settings(
        mock_mode=True,
        search_provider="mock",
        runs_dir=str(runs_dir),
    )
    original_client = extract.httpx.AsyncClient
    if guard_network:
        extract.httpx.AsyncClient = NetworkGuardClient  # type: ignore[assignment]
    try:
        await run_pipeline(run.id, bus, settings)
    finally:
        if guard_network:
            extract.httpx.AsyncClient = original_client
    snapshot = await bus.get_snapshot(run.id)
    events = [event.type async for event in bus.stream(run.id)]
    return snapshot, events


async def check() -> int:
    """Execute two happy-path runs and deterministic failure drills."""

    with tempfile.TemporaryDirectory(prefix="omnirush-phase8-") as temp:
        runs_dir = Path(temp)
        mock_runs: list[ReportRun] = []
        for index in range(2):
            snapshot, events = await run_case(
                "quantum computing 2026",
                runs_dir,
                guard_network=True,
            )
            if snapshot.status != "completed" or snapshot.outcome != "completed":
                raise RuntimeError(f"mock run {index + 1} did not complete: {snapshot.message}")
            if not snapshot.report_md or "## Sources" not in snapshot.report_md:
                raise RuntimeError(f"mock run {index + 1} did not produce a cited report")
            if "run_completed" not in events or "source_fetched" not in events:
                raise RuntimeError(f"mock run {index + 1} missed expected completion events")
            mock_runs.append(snapshot)

        zero, zero_events = await run_case("zero results drill", runs_dir)
        if (
            zero.outcome != "no_results"
            or zero.message != "No sources found. Try a different topic."
        ):
            raise RuntimeError("zero-results drill did not produce the friendly outcome")
        if "no_results" not in zero_events or zero.report_md:
            raise RuntimeError("zero-results drill invoked synthesis or omitted its event")

        dead, dead_events = await run_case("dead source drill", runs_dir)
        if dead.status != "completed" or "source_skipped" not in dead_events:
            raise RuntimeError("dead-source drill did not degrade gracefully")

        partial, partial_events = await run_case("synthesis timeout drill", runs_dir)
        if (
            partial.status != "completed"
            or not partial.partial
            or "synthesis_partial" not in partial_events
            or not partial.report_md
            or "Partial report" not in partial.report_md
        ):
            raise RuntimeError("synthesis-timeout drill did not preserve partial output")

        latest = mock_runs[-1]
        print("Phase 8 offline acceptance: PASS")
        print(f"mock_runs=2 status={latest.status} sources={latest.succeeded_sources}")
        print(f"dead_source=PASS skipped_event={'source_skipped' in dead_events}")
        print(f"zero_results=PASS outcome={zero.outcome}")
        print(f"synthesis_timeout=PASS partial={partial.partial}")
        print("stage timings (latest mock run):")
        for stage, timing in latest.stage_timings.items():
            budget = f"/{timing.budget_seconds:.0f}s" if timing.budget_seconds is not None else ""
            print(
                f"  {stage:12} {timing.elapsed_ms / 1000:.3f}s"
                f"{budget} within={timing.within_budget}"
            )
        print(
            f"total={latest.total_elapsed_ms / 1000:.3f}s/{Settings().total_budget_seconds:.0f}s "
            f"budget={latest.budget_status} "
            f"search_calls={latest.search_calls}/{latest.max_search_calls}"
        )
    return 0


def main() -> int:
    """Run the offline checks from the backend working directory."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    return asyncio.run(check())


if __name__ == "__main__":
    raise SystemExit(main())
