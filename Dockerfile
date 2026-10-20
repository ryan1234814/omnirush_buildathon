# Frontend build stage keeps the Docker build reproducible even though Phase 1 runs it separately.
FROM node:22.22.3-bookworm-slim AS frontend-build
WORKDIR /project/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12.11-slim-bookworm
WORKDIR /app

# WeasyPrint's runtime libraries are installed now so later PDF phases do not need a base-image
# change. The frontend artifact is copied as a build artifact for the same reason.
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        libcairo2 \
        libffi8 \
        libfontconfig1 \
        libgdk-pixbuf-2.0-0 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY --from=frontend-build /project/frontend/dist /app/frontend-dist
COPY README.md /app/README.md
COPY backend/pyproject.toml backend/uv.lock /app/backend/
RUN pip install --no-cache-dir uv==0.12.3 \
    && cd /app/backend \
    && uv sync --frozen --no-dev --no-install-project
COPY backend/app /app/backend/app

WORKDIR /app/backend
# The API serves the built frontend from the copied artifact, making the container the full app.
ENV STATIC_DIR=/app/frontend-dist
EXPOSE 8000
CMD ["/app/backend/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
