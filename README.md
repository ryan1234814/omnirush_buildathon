# One-Click Research Report Agent

Type a topic, watch an agent research the web, and receive a professional report with
deterministic inline citations. This repository currently contains **Phase 1**: the
reproducible backend configuration/health foundation and a frontend mission-control scaffold.

## Stack

- Python 3.12, FastAPI, and Uvicorn
- OpenAI-compatible API configuration through the `openai` SDK settings
- Tavily, Serper, or mock search provider settings (provider integrations arrive in later phases)
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

The `.env` file is local-only and is ignored by git. API keys are optional for Phase 1.

The backend also supports the alternative editable-install workflow requested by the product
plan:

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

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
