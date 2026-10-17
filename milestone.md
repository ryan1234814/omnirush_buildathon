# One-Click Research Report Agent — PRD & Phased Build Plan

## 1. Product Summary

**One-liner:** Type any topic → watch an agent search the web, read the best sources, and produce a professional, citation-backed report you can download as PDF — live, in front of your eyes.

**Why it wins the "Agents & AI Automation" track:** visible multi-step agency (judges *watch* the agent work), a tangible artifact at the end (cited report + PDF), and real business value (replaces hours of research).

**Confirmed decisions:**
| Layer | Choice | Rationale |
|---|---|---|
| Backend | Python 3.12, FastAPI, uvicorn | async-native, SSE built into starlette |
| LLM | OpenAI-compatible endpoint via `openai` SDK (base URL + model via env) | provider-agnostic; swap without code changes |
| Search | **Tavily** (`search` + `extract` endpoints), 1,000 free calls/mo — plenty for a week + demos. Env `SEARCH_PROVIDER=tavily\|serper\|mock` allows fallback | Tavily `extract` returns clean LLM-ready text, avoiding a Playwright/headless-browser failure surface entirely |
| Fetch fallback | `httpx` + `trafilatura` when Tavily extract fails for a URL | belt-and-suspenders, still no browser |
| Progress stream | **SSE** (Server-Sent Events), one-way agent→browser | simpler than WebSocket; reconnect via replayed snapshot |
| Report format | Markdown with numbered inline citations `[1]…[n]` backed by a deterministic source registry | enables citation validation + clean PDF |
| PDF | `markdown` (Py) → HTML → **WeasyPrint** with print CSS | pure Python, no LaTeX/pandoc system deps, styled output |
| Frontend | Vite + React + TypeScript | fast to build, easy SSE + markdown rendering |
| State | In-memory run registry + JSON snapshot persisted to disk per run | no DB migration risk; page refresh restores |
| Parallelism | `asyncio.gather` over bounded source batches | latency: cap end-to-end at ~90 s |

**Citation integrity (non-negotiable core):** the LLM never free-forms URLs. The pipeline builds a numbered **source registry** (`{id, url, title, excerpt}`), forces the model to cite only by `[id]`, then a **validator** strips/flags any `[n]` whose id isn't in the registry, and backfills the References section deterministically from the registry. Hallucinated citations become structurally impossible.

---

## 2. Target Architecture & File Layout

```
omnirush-report-agent/
├── .env.example                        # never real .env; commit example only
├── backend/
│   ├── pyproject.toml                  # uv-managed; deps: fastapi, uvicorn[standard], openai,
│   │                                   # httpx, tavily-python, trafilatura, markdown, weasyprint,
│   │                                   # pydantic-settings, pytest, pytest-asyncio, ruff
│   └── app/
│       ├── main.py                     # FastAPI app, CORS, mounts routers
│       ├── config.py                   # Settings via pydantic-settings (keys, model, SEARCH_PROVIDER, MOCK_MODE)
│       ├── models.py                   # Pydantic: TopicRequest, Source, SourceRegistry, ReportRun, Stage, RunEvent
│       ├── api/
│       │   ├── reports.py              # POST /api/reports, GET /api/reports/{id}, GET /api/reports/{id}/events (SSE),
│       │   │                           # GET /api/reports/{id}/report.md, GET /api/reports/{id}/report.pdf
│       │   └── health.py               # GET /api/health (also reports provider key config status)
│       ├── pipeline/orchestrator.py    # run_pipeline(run_id): stage sequence, emits events, try/except per stage
│       ├── pipeline/query_planner.py   # topic → 2–4 refined sub-queries (LLM, strict JSON)
│       ├── pipeline/search.py          # SearchProvider protocol + TavilySearch + SerperSearch + MockSearch
│       ├── pipeline/extract.py         # parallel Tavily-extract w/ httpx+trafilatura fallback, timeouts
│       ├── pipeline/ranker.py          # dedupe by URL, score = relevance*0.6 + content-quality*0.4, top-K
│       ├── pipeline/synthesizer.py     # excerpt-bounded cited generation (streaming)
│       ├── pipeline/citations.py       # registry build, validate_report(), strip invalid [n]
│       ├── pipeline/report_md.py       # assemble title/TOC/body/references markdown
│       ├── pdf/renderer.py             # markdown → HTML → WeasyPrint PDF (report.css)
│       ├── events/bus.py               # per-run asyncio.Queue pub/sub + snapshot store for SSE replay
│       ├── prompts/                    # ONE file per prompt, versioned constants
│       │   ├── query_plan.py  synthesis.py  ranking.py
│       ├── mock/fixtures/              # fixture_search.json + pages/*.html (curated offline corpus)
│       └── tests/                      # test_citations.py test_ranker.py test_pipeline_mock.py test_pdf.py
└── frontend/
    ├── index.html  vite.config.ts  package.json
    └── src/
        ├── App.tsx                     # state machine: idle → running → done → error
        ├── api/client.ts               # createReport(id), subscribeEvents(id) via EventSource
        ├── components/
        │   ├── TopicForm.tsx           # input + example-topic chips
        │   ├── ProgressTimeline.tsx    # live stage cards + per-source fetch status
        │   ├── ReportView.tsx          # react-markdown + remark-gfm, clickable [n] citations
        │   └── PdfDownload.tsx         # <a download href="/api/reports/{id}/report.pdf">
        └── styles                      # dark, high-contrast "mission control" demo look
```

**Conventions (enforced by ruff config + review):** full type hints on every function; all LLM calls use `response_format={"type":"json_object"}` where JSON is expected and are parsed into Pydantic models with a single retry on parse failure; every external HTTP call has an explicit timeout (search 10 s, extract 15 s, LLM 60 s) and never raises past its stage wrapper — stages degrade, the pipeline never crashes mid-run; no secrets in code (pydantic-settings from env only); no LangChain/LlamaIndex — plain SDKs, less magic, fewer version-drift bugs.

---

## 3. Phased Build Schedule (7 days, risk-first)

Each phase is independently testable and ends with an **ACCEPTANCE CHECKPOINT — do not start the next phase until it passes.** Every coding-agent instruction below is written to be unambiguous.

### Phase 1 — Scaffold + Config + Health (Day 1 AM, ~1.5 h)
1. Create repo layout above; `git init`; `.gitignore` (`.env`, `__pycache__`, `dist`, `*.pdf`).
2. `backend/pyproject.toml` with all deps pinned; install with `uv sync` (document `pip install -e .` alternative).
3. `config.py`: `Settings` reading `OPENAI_API_KEY`, `OPENAI_BASE_URL` (default OpenAI), `LLM_MODEL`, `TAVILY_API_KEY`, `SERPER_API_KEY`, `SEARCH_PROVIDER` (default `tavily`), `MOCK_MODE` (bool). `.env.example` documents each with the env var's purpose.
4. `main.py` + `health.py`: `GET /api/health` returns `{status, search_provider, llm_configured, mock_mode}`.
5. Frontend scaffold: `npm create vite@latest frontend -- --template react-ts`; add `react-markdown`, `remark-gfm`, `recharts` (skip recharts unless wanted — default: skip).

**✅ Checkpoint:** `uvicorn app.main:app` boots; `curl /api/health` shows correct provider config; `npm run dev` renders "hello" page; keys absent → health says `llm_configured: false` without crashing.

### Phase 2 — De-risk the Two Scary Integrations (Day 1 PM, ~2 h) ⚠️ *do this before any UI*
1. `search.py`: define `SearchProvider` protocol (`async def search(query, max_results) -> list[SearchResult]`). Implement `TavilySearch` using `tavily-python` (search with `include_answer=True, search_depth="advanced"`). Wire `MockSearch` (loads `mock/fixtures/fixture_search.json`).
2. `query_planner.py` + `prompts/query_plan.py`: one LLM call converting the topic into 2–4 sub-queries; strict JSON schema `{sub_queries: [string]}`; on any failure → fall back to `[topic]`. Never block the pipeline.
3. Throwaway script `backend/scripts/integration_check.py`: topic in → prints planned sub-queries, raw search results, and one Tavily-extract call's cleaned text. Run it 10 times against real API.

**✅ Checkpoint:** 10 consecutive successful real-API runs, each < 20 s; error paths verified by temporarily breaking the key (clean message, no stack-trace crash). **If Tavily is unreliable here → switch `SEARCH_PROVIDER=serper` now (2,500 free queries) — do not discover this on day 5.**

### Phase 3 — Extraction, Dedupe, Ranking (Day 2, ~3 h)
1. `extract.py`: `async def fetch_sources(results) -> list[Source]` using `asyncio.gather(*tasks)` where each task: 15 s timeout, try Tavily `extract` first; on failure/empty → `httpx GET` (mobile-UA header, 10 s timeout) → `trafilatura.extract`; on total failure return `None` (skip, never raise).
2. `ranker.py`: normalize URLs (strip utm/query for dedupe), dedupe, score `0.6*search_relevance + 0.4*quality` (quality = length curve + trafilatura `scores`/meta flags), keep top-K (default K=6, env `TOP_K`).
3. Unit tests for ranker: dedupe variants, short-content penalty, empty input.

**✅ Checkpoint:** script from Phase 2 extended to full fetch+rank: 6 clean sources extracted in parallel in < 25 s wall time; one deliberately dead URL in fixtures is skipped with a warning and the run still completes. `MOCK_MODE=1` runs the whole phase against fixtures with zero network.

### Phase 4 — Citation-Strict Synthesis (Day 3, ~4 h) — *the heart of the product*
1. `citations.py`:
   - `build_registry(sources) -> SourceRegistry` assigning ids 1..K, each entry `{id, url, title, excerpt}` (excerpt ≤ 1,500 words; enforce total context budget ≤ ~24k input tokens by trimming lowest-ranked sources first).
   - `validate_report(md, registry) -> (clean_md, removed_cites)` regex-scans all `[n]`, strips any id outside 1..K, appends nothing manually.
2. `prompts/synthesis.py` (pin the exact rules — this is what the coding agent must not "improvise"): system prompt demands a markdown report with `##` sections, EVERY factual sentence ends with `[n]` referencing ONLY provided excerpt ids, no URLs written by the model, no outside knowledge unless marked `*(unverified)*`. Pass excerpts as fenced blocks labeled `[1] TITLE — URL` … in the user message. Stream (`stream=True`).
3. `synthesizer.py`: `async def stream_report(topic, registry) -> AsyncIterator[str]` yields tokens; caller accumulates; after completion run `validate_report`, then `report_md.assemble()` appends `## Sources` — each entry `**[n] Title** — [url](url)` generated *from the registry data, never from the model*.
4. Unit tests: fabricated `[7]` with K=6 is stripped; a clean report passes untouched; references section matches registry exactly.

**✅ Checkpoint:** run against mock fixtures → produce `report.md` on disk; human-audit two real-topic reports: zero dead citations, every `[n]` jumps to a listed source, excerpts actually support the claims. **Do NOT proceed until citation integrity tests pass** — everything downstream just displays/prints this file.

### Phase 5 — Orchestrator + Run Registry + SSE (Day 4, ~3 h)
1. `models.py`: `ReportRun {id, topic, status, stage, sources, report_md, created_at, error}`; `Stage` enum (`PLANNING, SEARCHING, EXTRACTING, RANKING, SYNTHESIZING, RENDERING, DONE, FAILED`).
2. `events/bus.py`: dict `run_id -> {queue, events_history, snapshot}`; every emitted event gets a monotonic `seq`; SSE endpoint sends `data: {json}\n\n` with `id: seq` and supports `Last-Event-ID` replay from history (refresh-safe demo).
3. `orchestrator.py`: sequential stages, each wrapped `try/except` → emit `stage_started`/`stage_completed`/`stage_failed` + per-source events (`source_fetched {url, ok, bytes}`); `asyncio.create_task` launched from `POST /api/reports` (returns `run_id` immediately, 202). Persist JSON snapshot on every stage boundary and on completion (survives within-process restart needs; document that uvicorn worker count must stay 1 for the demo).
4. Endpoints in `api/reports.py`: `POST /api/reports {topic}`, `GET /api/reports/{id}`, `GET /api/reports/{id}/events` (`EventSourceResponse`), `GET /api/reports/{id}/report.md`.
5. Integration test with `MOCK_MODE=1`: POST → consume SSE stream → assert event sequence complete and report non-empty.

**✅ Checkpoint:** `curl -N` on the events endpoint shows ordered stage events live in terminal; a full mock-mode run completes end-to-end via API only (no UI yet).

### Phase 6 — Frontend: Live "Mission Control" UI (Day 5, ~4 h)
1. `api/client.ts`: typed `EventSource` wrapper with auto-reconnect (3 tries) and last-seq tracking.
2. `App.tsx` state machine: `idle → running → done → error`; `running` shows `ProgressTimeline` (stage cards light up; sources appear as fetched checkmarks) and streams report tokens into `ReportView` incrementally.
3. `ReportView.tsx`: `react-markdown` + `remark-gfm`; custom renderer mapping `[n]` to `<sup><a href="#source-n">` anchors; `Sources` section cards with favicon (Google s2 favicons URL) + domain + title.
4. `TopicForm.tsx`: input + 4 example-topic chips ("Quantum computing 2026", …) — pre-load these for the stage demo so you never type live.
5. Styling pass: dark theme, big status glyphs — must read clearly from a projector 5 m away.

**✅ Checkpoint:** full mock-mode run in browser: watch timeline light up, report types itself out, citations clickable, refresh mid-run restores state. Screenshot it — this is your demo.

### Phase 7 — PDF Export (Day 6 AM, ~2 h)
1. `pdf/renderer.py`: `markdown.markdown(md, extensions=["tables","footnotes"])` → wrap in HTML template → WeasyPrint with `report.css` (A4, running page numbers, styled `[n]` sup anchors, sources list with truncated-but-clickable URLs, avoid-break on section headers).
2. Endpoint `GET /api/reports/{id}/report.pdf` (`FileResponse`, generated lazily then cached to disk at `data/runs/{id}.pdf`); `PdfDownload.tsx` links it.
3. Test: PDF for mock report renders, contains "Sources", page count > 2. (WeasyPrint system deps: install via `brew install weasyprint` on macOS dev machine / pango in Docker — pin and document on day 6, not on stage.)

**✅ Checkpoint:** one click from finished report → downloaded, professional-looking PDF. Judge-facing artifact complete.

### Phase 8 — Hardening + Demo Rehearsal (Day 6 PM → Day 7)
1. **Fixtures refresh**: curate `mock/fixtures/pages/` with 6 high-quality saved pages for the exact demo topic. Verify `MOCK_MODE=1` end-to-end with zero network (kill wifi and run it — this is the stage-insurance demo).
2. Rate-limit + quota guard: `SearchProvider` wraps 429 with one retry after backoff; hard cap of `MAX_SEARCH_CALLS=8` per run logged on completion.
3. Failure drills (each must degrade gracefully, not 500): search returns 0 results → "Try a different topic" state; LLM timeout mid-synthesis → partial report delivered with note; dead source → skipped event visible in UI.
4. Latency budget check on real API with demo topic: planning ≤8 s, search ≤5 s, extract ≤25 s, synthesis ≤45 s ⇒ ≤~85 s total. If over: reduce `TOP_K` to 5, trim excerpt budget to 1,200 words, shorten report length instruction.
5. 3 full dress rehearsals of the exact demo script (chips → run → narrate timeline → click citation → download PDF → switch to mock-mode "resilience" talking point). **48-hour feature freeze before demo.**

**✅ Final acceptance:** 5 consecutive real-API runs + 2 mock runs, all complete, all citation-valid, worst-case ≤ 2 min.

---

## 4. Dependency Map

- P1 → everything. **P2 gates P3** (never build extraction on unvalidated search). P3 → P4 (registry needs sources). **P4 gates P5–P7** (report is the product; PDF/UI are projections of it). P5 → P6, P7. P8 wraps all.
- Parallelizable: P6 frontend skeleton (static components, mocked SSE) can be built during P5 by a second person; prompt-tuning in P4 can run against existing mock fixtures anytime.

## 5. Top Risks & Mitigations

| Risk | Mitigation (baked into plan) |
|---|---|
| Hallucinated citations (kills credibility) | Registry-enforced citation + `validate_report` (P4) + unit tests gating progress |
| Search API outage/ quota mid-demo | Provider abstraction + Serper fallback chosen in P2 checkpoint + **mock mode** full-offline run (P8) |
| Scraping blocked/JS-only pages | Tavily `extract`