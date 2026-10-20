# Hyperframes Composition Brief: Omnirush

## Objective
Create a 20.4-second launch-style brag video for Omnirush, a one-click research agent with deterministic citations.

## Output
- Composition directory: `brag-output-2026-10-20-1100/composition/`
- Rendered video: `brag-output-2026-10-20-1100/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 20.4 seconds

## Source Material
- Project root: `/Users/ryangeorge/omnirush buildathon`
- Primary files read: `README.md`, `frontend/src/App.tsx`, `frontend/src/App.css`, `frontend/src/index.css`, `frontend/src/components/*`, `demo/mission-control-complete.png`, live UI screenshot, `backend/data/runs/*.json`
- Product name: Omnirush
- Tagline / strongest claim: "One-click research report agent" / "Research that shows its work"
- Key UI moment to recreate: the command deck → live run deck pipeline → report workspace → citation integrity badge
- Copy that must appear verbatim:
  - ASK THE SYSTEM ANYTHING.
  - Launch a citation-backed research operation
  - Quantum computing 2026
  - Start research
  - WATCH EVERY STAGE.
  - US$2.01B / IN 2026 / up from US$1.51B in 2025 / 33.1% CAGR
  - CITATION INTEGRITY: 26 VALIDATED / 1 HALLUCINATED REMOVED
  - UNKNOWN SOURCE
  - CITATION REMOVED
  - RESEARCH THAT SHOWS ITS WORK.
  - Replayable runs · citation-safe output · one-click PDF.

## Creative Direction
- Tone preset: default
- Creative direction: mission-control zine printed on warm paper — sticker labels, hard ink shadows, comic display type, dead-serious proof
- Interpretation: quick cuts, snappy entrances, one idea per scene. No ironic distance and no generic SaaS copy. Humor comes from applying mission-control gravity to a research report.
- Angle: research agents ask for trust; Omnirush shows receipts, then deletes the citation it cannot verify.
- Hook: the product's own command deck line slammed in as giant ink type.
- Outro / punchline: logo + "RESEARCH THAT SHOWS ITS WORK."
- Avoid:
  - Generic SaaS language
  - Abstract filler visuals
  - Unrelated visual redesign
  - Dark mission-control styling (the current UI is warm paper + ink + comic type)

## Visual Identity
- Background: `#FFF8EE` (warm paper) with `#0C0E0F` dot grid
- Text: `#0C0E0F`
- Accent: `#FBC93E` yellow, `#FFE23A` tape, `#22AC5F` green, `#EF4225` red, `#AD69FF` plum, `#4080FB` blue, `#F57EB4` pink
- Display font: Bangers (local woff2)
- Body font: Space Grotesk (local woff2)
- Label font: Titan One (local woff2)
- Mono font: Space Mono (local woff2)
- Visual references from the project:
  - Black rounded sticker nav bar with yellow brand mark
  - Yellow command deck card on paper with ink dot grid
  - Hard offset shadows (`6px 6px 0 #0C0E0F`)
  - Hand-inked pipeline wire with six circular nodes
  - Oversized Bangers headline with layered text shadow
  - Plum citation pills, mint validated badge, black/yellow tape strip

## Storyboard
Use the storyboard in `brag-output-2026-10-20-1100/brag-plan.md` as the creative contract.

Scene summary:
1. Command deck hook — 3.2s — headline, command card, cursor click
2. Watch every stage — 4.0s — six pipeline nodes + telemetry
3. The report types itself — 4.2s — US$2.01B stat + three source cards
4. It deletes its own hallucinations — 4.7s — [9] flagged and removed + integrity badge
5. Research that shows its work — 4.3s — logo, tagline, footer

## Audio
- Audio role: warm, upbeat bed with crisp UI accents
- Audio arc: hook → mechanical build through pipeline → evidence stack → one hard impact at citation removal → resolved logo
- Music: `assets/music/happy-beats-business-moves-vol-10-by-ende-dot-app.mp3`
- Music treatment: volume 0.32, bed starts at 0; dip slightly at the citation-removal stamp (12.0–13.2s); fade out over the last 0.5s
- Music cue guidance: bundled preset `happy-beats-business-moves-vol-10-by-ende-dot-app.music-cues.json` (109.96 BPM). Use node beats 3.55/4.10/4.64/5.19/5.74/6.28, source cards 8.22/8.73/9.29, badge near 14.73, final logo on strong cue 18.01 (±0.15s). Readability wins over cues.
- Audio-reactive treatment: subtle; `assets/music/audio-data.js` drives the paper halo RMS/scale behind the report and final logo. No waveform/equalizer graphics.
- Audio-coupled moments:
  - Scene 1 — cursor click on Start research; soft word drops
  - Scene 2 — one tick per pipeline node (beat-grid)
  - Scene 3 — three card-place sounds; short keypress cluster for report line
  - Scene 4 — impact on UNKNOWN SOURCE / CITATION REMOVED; soft bell on badge
  - Scene 5 — bell on logo, music fade
- SFX selection guidance: use local `assets/sfx/*`; interface clicks/drops, casino card place, keyboard keypresses, one impact soft/medium, one bong. Keep SFX at 0.55–0.8.
- SFX analysis guidance: `/Users/ryangeorge/.agents/skills/brag/assets/sfx/sfx-analysis.md`
- Exact SFX choice: implementation decides filenames/timestamps based on animation.
- Audio files: already copied into `composition/assets/`.

## Hyperframes Instructions
Load the composition-building Hyperframes domain skills — `hyperframes-core` (composition contract + `data-*` timing), `hyperframes-animation` (motion), `hyperframes-creative` (design spec, beats, audio-reactive), `hyperframes-keyframes` (seek-safe keyframes), and `hyperframes-cli` (lint/check/render). /brag is its own workflow: do not enter the `hyperframes` entry-point intent interview and do not route into its generic promo / launch-video workflow. Prefer native Hyperframes conventions over anything in `/brag`.

Requirements:
- Show at least one real UI, copy, or visual element from the source project.
- Keep all text readable in the final render.
- Keep the video within 15-25 seconds.
- Include the planned music/SFX layer.
- Treat `/brag` audio notes as guidance, not a fixed cue sheet.
- Use only 1-3 strong cue locks; the final logo is locked to 18.01s.
- Run `npx hyperframes check` before render.
- Keep creation and rendering local.
