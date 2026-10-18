# One-Click Research Report Agent

Type a topic, watch an agent research the web, and receive a professional report with
deterministic inline citations. The browser UI is a live mission-control view with replayable
progress, incremental Markdown rendering, source cards, refresh recovery, and one-click PDF export.

## Stack

- Python 3.12, FastAPI, and Uvicorn
- OpenAI-compatible API configuration through the `openai` SDK settings
- Tavily or mock search providers for the Phase 2 integration seam
- Vite, React, and TypeScript

## Prerequisites

- [uv](https://docs.astral.sh/uv/) for the pinned Python environment
- Node.js 22 or newer and npm

Python 3.12 is pinned in `.python-version`. `uv` can download that interpreter when it is not
already installed locally.

## Setup

```sh
cp .env.example .env
cd backend
uv sync
cd ../frontend
npm install
```

The `.env` file is local-only and is ignored by git. API keys are optional for offline development;
set `OPENAI_API_KEY` and `TAVILY_API_KEY` in `.env` to run the real integration check.

The backend also supports the alternative editable-install workflow requested by the product
plan:

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

## Phase 2 integration check

The planner makes one JSON-mode LLM call and falls back to the original topic if the key, request,
or response is invalid. Search providers share one async interface; `MOCK_MODE=true` uses the
committed fixture and makes no network calls.

Run the deterministic offline check:

```sh
cd backend
MOCK_MODE=true SEARCH_PROVIDER=mock uv run --offline python -m scripts.integration_check "quantum computing 2026"
```

Run the real Tavily check after configuring both API keys:

```sh
cd backend
uv run python -m scripts.integration_check "quantum computing 2026"
```

The script prints planned sub-queries, normalized raw search results, and one Tavily extract. A
provider failure is reported as a short error with a non-zero exit code rather than a traceback.
The real-API ten-run checkpoint is intentionally an operator action because credentials and quota
are not stored in this repository.

Phase 3 extends the check with concurrent extraction, URL deduplication, quality ranking, and a
`TOP_K` cap (default `6`). Tavily extraction has a 15-second timeout per source. Failed or empty
Tavily extracts fall back to an HTTP fetch with a mobile user agent and a 10-second timeout, then
`trafilatura`; an individual dead source is skipped without failing the run.

Run the complete offline Phase 3 check:

```sh
cd backend
MOCK_MODE=true SEARCH_PROVIDER=mock TOP_K=6 \
  uv run --offline python -m scripts.integration_check "quantum computing 2026"
```

## Phase 4–5 report API

The backend now builds a bounded citation registry, validates generated `[n]` citations, and
generates the `## Sources` section deterministically from registry data. It also exposes a
background report API with replayable Server-Sent Events. Snapshots are persisted as JSON under
`data/runs` (override with `RUNS_DIR`); run the demo with one Uvicorn worker so the in-memory event
bus and task registry remain consistent. `SYNTHESIS_CONTEXT_TOKENS` defaults to `3000` so the
default Groq configuration remains below its 8,000-token-per-minute request limit; it can be
raised for providers with larger limits, up to the registry's 24,000-token safety budget.

Run the complete offline API flow:

```sh
cd backend
MOCK_MODE=true SEARCH_PROVIDER=mock \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
run_id=$(curl -sS -X POST http://127.0.0.1:8000/api/reports \
  -H 'content-type: application/json' \
  -d '{"topic":"quantum computing 2026"}' | python -c \
  'import json,sys; print(json.load(sys.stdin)["id"])')
curl -N http://127.0.0.1:8000/api/reports/$run_id/events
curl -sS http://127.0.0.1:8000/api/reports/$run_id/report.md
```

The SSE stream emits stage events, per-source `source_fetched` events, streamed `report_token`
events, and a terminal `run_completed` or `run_failed` event. `Last-Event-ID` (or the
`last_event_id` query cursor used by the frontend wrapper) replays missed events. The frontend
stores the current run ID in local storage, so refreshing during a one-worker mock run rebuilds
the timeline and report from the replay stream.

Generate the Phase 4 checkpoint artifact without any network access:

```sh
cd backend
uv run --offline python -m scripts.mock_report_check --output report.md
```

## Live UI and PDF export

When the mock backend is running, open <http://localhost:5173>, select the pre-loaded
`Quantum computing 2026` example, and click **Start research**. The timeline lights each stage,
source fetches appear as checkmarks, and the report types itself into the citation-aware viewer.
The platform dashboard also includes a command deck, live event stream, system telemetry, browser-local
recent-run archive, research capability launcher, searchable source intelligence, and projector mode.
Finished reports expose **Save as PDF**, which calls `GET /api/reports/{id}/report.pdf`. The first
request renders with WeasyPrint and atomically caches the artifact as `data/runs/{id}.pdf`; later
requests serve the cached file. The Docker image includes the Linux Pango/Cairo libraries needed
by WeasyPrint. On macOS, install WeasyPrint's native dependencies before running a real PDF export
(for example, `brew install weasyprint`), use the reproducible Docker image, or use the optional
LibreOffice fallback when `soffice` is already available on the developer machine. Docker remains
the recommended path for release-equivalent output; LibreOffice only exists to keep the local
download flow usable when Pango/GObject are unavailable.

## Run

Start the API from the repository root:

```sh
cd backend
uv run uvicorn app.main:app --reload
```

In a second terminal, start the frontend:

```sh
cd frontend
npm run dev
```

The frontend is available at <http://localhost:5173>. The Phase 1 API health check is
<http://localhost:8000/api/health>. With no keys configured, it returns `llm_configured: false`
and does not crash.

## Test and lint

After dependencies have been installed, the single project check is:

```sh
make test
```

It runs the backend tests and Ruff checks offline, followed by the frontend TypeScript/Vite
production build. Individual checks are:

```sh
cd backend && uv run --offline pytest
cd backend && uv run --offline ruff check .
cd frontend && npm run lint
cd frontend && npm run build
```

## Container

Build and run the API container with:

```sh
docker build -t omnirush-report-agent .
docker run --rm -p 8000:8000 --env-file .env omnirush-report-agent
```

The container exposes the same health endpoint on port 8000. The frontend remains a separate
Vite development server during Phase 1.

## Deploy

Build the frontend with `npm run build`, deploy `frontend/dist` to a static host, and deploy the
FastAPI container (or the `backend` package with Uvicorn) to a Python 3.12 service. Configure the
same environment variables from `.env.example` in the service's secret manager.
