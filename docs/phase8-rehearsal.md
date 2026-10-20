# Phase 8 demo rehearsal runbook

This is the judge-facing script for the final rehearsal. Run it three times before feature freeze;
record the date, git commit, provider mode, total duration, and any issue after each run.

## Exact demo script

1. Start the backend in deterministic mock mode and start the frontend.
2. Click the **Quantum computing 2026** chip; do not type into the live form.
3. Click **Start research**.
4. Narrate the stage rail: planning, search, extraction, ranking, synthesis, rendering.
5. Point out the fetched-source checkmarks and the event stream.
6. Click an inline citation and show the matching source card/domain.
7. Click **Save as PDF** and confirm the downloaded artifact opens.
8. Switch to the `zero results drill` and `dead source drill` topics to demonstrate:
   - the **Try a different topic** state;
   - a visible skipped/dead source event.
9. Run the `synthesis timeout drill` and show the incomplete-report note plus disabled PDF export.
10. Return to `Quantum computing 2026` and leave the dashboard in projector mode.

## Acceptance commands

Offline stage-insurance check; this makes no HTTP requests from the mock extractor:

```sh
make phase8-check
```

Real-provider latency and acceptance check; configure credentials first:

```sh
cd backend
uv run python -m scripts.latency_check --runs 5 --topic "quantum computing 2026"
```

The real check rejects failed/partial runs, missing `## Sources`, runs over two minutes, and prints
planning/search/extraction/synthesis timing against the 8/5/25/45 second budgets. A run over the
85-second target remains visible as a warning rather than being hidden.

## Rehearsal log

| Rehearsal | Commit | Mode | Total | Result | Notes |
|---|---|---|---:|---|---|
| 1 (2026-10-20) | db71d88 (working tree) | mock (`make phase8-check`) | 0.3 s | PASS | All drills green (zero results, dead source, synthesis timeout); 6 sources; pipeline total 0.006 s |
| 2 (2026-10-20) | db71d88 (working tree) | mock (`make phase8-check`) | 0.3 s | PASS | Repeat run, identical results; search calls 1/8; budget `within_budget` |
| 3 (2026-10-20) | db71d88 (working tree) | mock HTTP+SSE (`POST /api/reports` → event stream) | 1 s | PASS | 28 ordered SSE events; `report_evaluated` → `run_completed`; snapshot and `report.json` carry integrity fields |

Rehearsals 1–3 are the automated mock dress rehearsals (deterministic, zero network). The
three-step browser script above and the five-run real-API `latency_check` remain operator actions
before the demo (projector legibility, clicks, and provider credentials cannot be automated here).
Feature freeze additionally requires one docker-compose up check (`make docker-up`) so the
judge-facing container path is exercised outside CI.

Freeze feature changes 48 hours before the demo. After freeze, only fix blockers, rerun `make test`,
and repeat the exact script above.
