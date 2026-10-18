"""Measure real API report runs against the Phase 8 latency budget."""

from __future__ import annotations

import argparse
import asyncio
import re
import time

import httpx

STAGE_BUDGETS = {
    "PLANNING": 8.0,
    "SEARCHING": 5.0,
    "EXTRACTING": 25.0,
    "SYNTHESIZING": 45.0,
}
TOTAL_BUDGET = 85.0
ACCEPTANCE_LIMIT = 120.0


async def run_once(client: httpx.AsyncClient, topic: str, timeout: float) -> float:
    """Create one report, wait for its snapshot, and print its telemetry."""

    response = await client.post("/api/reports", json={"topic": topic})
    response.raise_for_status()
    run_id = response.json()["id"]
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        snapshot_response = await client.get(f"/api/reports/{run_id}")
        snapshot_response.raise_for_status()
        snapshot = snapshot_response.json()
        if snapshot["status"] in {"completed", "failed"}:
            elapsed = time.monotonic() - started
            print(
                f"run={run_id} status={snapshot['status']} outcome={snapshot.get('outcome')} "
                f"wall={elapsed:.2f}s total={snapshot.get('total_elapsed_ms', 0) / 1000:.2f}s"
            )
            for stage, budget in STAGE_BUDGETS.items():
                timing = snapshot.get("stage_timings", {}).get(stage)
                if timing is None:
                    continue
                seconds = timing.get("elapsed_ms", 0) / 1000
                print(f"  {stage.lower():12} {seconds:6.2f}s / {budget:5.2f}s")
            if snapshot["status"] != "completed":
                raise RuntimeError(snapshot.get("error") or "real API run failed")
            if snapshot.get("partial"):
                raise RuntimeError("real API run completed with a partial report")
            report = snapshot.get("report_md") or ""
            if "## Sources" not in report:
                raise RuntimeError("real API report did not contain a Sources section")
            body = report.split("## Sources", 1)[0]
            citations = {int(value) for value in re.findall(r"\[(\d+)\]", body)}
            source_ids = {int(source["id"]) for source in snapshot.get("sources", [])}
            if not citations.issubset(source_ids):
                missing = citations - source_ids
                raise RuntimeError(f"report contains citations without registry entries: {missing}")
            total = snapshot.get("total_elapsed_ms", 0) / 1000
            if total > ACCEPTANCE_LIMIT:
                raise RuntimeError(
                    f"real API run exceeded the {ACCEPTANCE_LIMIT:.0f}s acceptance limit"
                )
            return total
        await asyncio.sleep(0.25)
    raise TimeoutError(f"run {run_id} did not finish within {timeout:.0f}s")


async def check(topic: str, base_url: str, runs: int) -> int:
    """Run the requested number of real API rehearsals."""

    totals: list[float] = []
    async with httpx.AsyncClient(base_url=base_url, timeout=15.0) as client:
        for _ in range(runs):
            totals.append(await run_once(client, topic, ACCEPTANCE_LIMIT))
    print(f"real_api_runs={runs} worst_total={max(totals):.2f}s budget={TOTAL_BUDGET:.2f}s")
    if max(totals) > TOTAL_BUDGET:
        print("WARNING: a run exceeded the target budget; consider TOP_K=5 and shorter excerpts.")
    return 0


def main() -> int:
    """Run real API latency checks from the backend working directory."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--topic", default="quantum computing 2026")
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    return asyncio.run(check(args.topic, args.base_url, args.runs))


if __name__ == "__main__":
    raise SystemExit(main())
