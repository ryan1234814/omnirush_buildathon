# Hyperframes Composition Brief: Omnirush — 60s

## Objective
Create a 60-second launch-style brag video for Omnirush, a one-click research agent with deterministic citations and a full post-report toolkit.

## Output
- Composition directory: `brag-output-2026-10-20-122645/composition/`
- Rendered video: `brag-output-2026-10-20-122645/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 60.0 seconds

## Source Material
- Project root: `/Users/ryangeorge/omnirush buildathon`
- Primary files read: `README.md`, `frontend/src/App.tsx`, `frontend/src/components/ReportTools.tsx`, `frontend/src/components/PdfDownload.tsx`, `backend/data/runs/*.json`
- Product name: Omnirush
- Tagline / strongest claim: "Research that shows its work"
- Key UI moments: command deck → live run deck pipeline → report workspace → citation integrity badge → coverage round → follow-up chat → compare runs → schedules → export formats → notifications → outro.
- Copy that must appear verbatim:
  - ASK THE SYSTEM ANYTHING.
  - Launch a citation-backed research operation
  - WATCH EVERY STAGE.
  - US$2.01B / IN 2026 / up from US$1.51B in 2025 / 33.1% CAGR
  - CITATION INTEGRITY: 26 VALIDATED / 1 HALLUCINATED REMOVED
  - UNKNOWN SOURCE / CITATION REMOVED
  - SELF-EVALUATING / RESEARCH ROUND 2 / MAX_SEARCH_CALLS
  - FOLLOW-UP CHAT / Ask about the evidence / Ask follow-up
  - COMPARE RUNS / See what changed
  - SCHEDULE / Run it again
  - ALTERNATE FORMATS / Export this report
  - PDF, Markdown, HTML, Plain text, JSON, Executive summary, Blog post, LinkedIn digest, Marp slides
  - NOTIFICATIONS / Delivery updates
  - RESEARCH THAT SHOWS ITS WORK.

## Creative Direction
- Tone preset: default
- Creative direction: mission-control zine printed on warm paper — sticker labels, hard ink shadows, comic display type, dead-serious proof
- Interpretation: quick cuts, snappy entrances, one idea per scene. No generic SaaS copy.
- Angle: research agents ask for trust; Omnirush shows receipts, then keeps working after the report.
- Hook: the product's own command deck line slammed in as giant ink type.
- Outro: logo + "RESEARCH THAT SHOWS ITS WORK." + capability recap.

## Visual Identity
- Background: `#FFF8EE` warm paper with `#0C0E0F` dot grid
- Text: `#0C0E0F`
- Accent: `#FBC93E` yellow, `#FFE23A` tape, `#22AC5F` green, `#EF4225` red, `#AD69FF` plum, `#4080FB` blue, `#F57EB4` pink
- Display font: Bangers; body: Space Grotesk; label: Titan One; mono: Space Mono
- Reuse: black sticker nav bar, yellow command card, hard offset shadows, inked pipeline wire, plum citation pills, mint validated badge, black/yellow tape.

## Storyboard
Use `brag-output-2026-10-20-122645/brag-plan.md` as the creative contract.

Scene summary:
1. Command deck hook — 3.2s — headline, command card, cursor click
2. Watch every stage — 4.0s — six pipeline nodes + telemetry
3. The report writes itself — 4.2s — US$2.01B stat + three source cards
4. It deletes its own hallucinations — 5.0s — [9] flagged and removed + integrity badge
5. It researches its own gaps — 5.4s — coverage audit + research round 2
6. Ask the evidence a follow-up — 5.6s — grounded chat + citation registry
7. See what changed between runs — 5.6s — diff rows + source churn
8. Put the research on repeat — 5.6s — schedule form + run queue
9. One report, nine ways out — 9.0s — nine export tiles
10. And it tells you when it's done — 4.8s — notifications + delivery channels
11. Research that shows its work — 7.6s — logo, tagline, recap, final stamp

## Audio
- Audio role: warm, upbeat bed with crisp UI accents
- Audio arc: hook → mechanical build through pipeline → evidence stack → one hard impact at citation removal → feature run → resolved logo
- Music: `assets/music/happy-beats-business-moves-vol-10-by-ende-dot-app.mp3` (60.00s)
- Music treatment: volume 0.38, bed starts at 0; dip slightly at the citation-removal stamp; fade out over the last 0.5s
- Music cue guidance: bundled vol-10 preset (109.96 BPM). Pipeline nodes 3.55/4.10/4.64/5.19/5.74/6.28; source cards 8.22/8.73/9.29; badge near 14.73; gap impact 17.72; export tiles 39.25–41.65; final logo at 54.01.
- Audio-reactive treatment: `assets/music/audio-data.js` drives the paper glow RMS/scale. No waveform graphics.
- Audio-coupled moments:
  - Scene 1 — cursor click on Start research; soft word drops
  - Scene 2 — one tick per pipeline node
  - Scene 3 — three card-place sounds; keypress cluster
  - Scene 4 — impact on UNKNOWN SOURCE / CITATION REMOVED; bell on badge
  - Scene 5 — gap impact + round stage ticks + bell on round badge
  - Scene 6 — send click, reply drop, citation select, registry bell
  - Scene 7 — compare click + four diff drops
  - Scene 8 — schedule click + three card places
  - Scene 9 — nine rapid tile drops + PDF bell
  - Scene 10 — notification bell + read click + three channel drops
  - Scene 11 — logo bell, recap drop, footer drop
- SFX selection: local `assets/sfx/*`; keep SFX at 0.42–0.75, below the music bed peaks.

## Hyperframes Instructions
- Follow `hyperframes-core` (composition contract + `data-*` timing), `hyperframes-animation` (motion), `hyperframes-creative`, `hyperframes-keyframes`, and `hyperframes-cli`.
- Show real UI, copy, and visual elements from the source project.
- Keep all text readable in the final render.
- Include the planned music/SFX layer.
- Run `npx hyperframes check` before render.
- Keep creation and rendering local.
