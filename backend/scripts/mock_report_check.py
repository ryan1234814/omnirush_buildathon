"""Generate a citation-validated Phase 4 report from offline fixtures."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.events.bus import EventBus
from app.models import ReportRun
from app.pipeline.orchestrator import run_pipeline


async def generate_report(output: Path) -> Path:
    """Run the full mock pipeline and write the assembled Markdown report."""

    settings = Settings(
        mock_mode=True,
        search_provider="mock",
        runs_dir=str(output.parent / "data" / "runs"),
    )
    bus = EventBus()
    run = ReportRun(
        id="mock-check",
        topic="quantum computing 2026",
        created_at=datetime.now(UTC),
    )
    await bus.register(run)
    await run_pipeline(run.id, bus, settings)
    snapshot = await bus.get_snapshot(run.id)
    if snapshot.status != "completed" or not snapshot.report_md:
        raise RuntimeError(snapshot.error or "mock report did not complete")
    output.write_text(snapshot.report_md, encoding="utf-8")
    return output


def main() -> int:
    """Generate ``report.md`` from the backend working directory."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("report.md"))
    args = parser.parse_args()
    output = asyncio.run(generate_report(args.output))
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
