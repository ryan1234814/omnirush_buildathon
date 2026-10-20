# One Dockerfile, two targets:
#   docker build .                          -> all-in-one container (API + built UI), local/demo
#   docker build --build-arg INCLUDE_FRONTEND=false \
#     --build-arg UV_EXCLUDE="--no-emit-package weasyprint --no-emit-package scrapling" .
#                                           -> slim backend-only image for Render (no UI, no
# WeasyPrint/Scrapling natives; PDF export and the Scrapling fallback are skipped there)
ARG INCLUDE_FRONTEND=true
ARG PORT=8000

FROM node:22.22.3-bookworm-slim AS frontend-build-false
FROM node:22.22.3-bookworm-slim AS frontend-build-true
WORKDIR /project/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12.11-slim-bookworm AS build-true
COPY --from=frontend-build-true /project/frontend/dist /app/frontend-dist

FROM python:3.12.11-slim-bookworm AS build-false

FROM python:3.12.11-slim-bookworm
ARG INCLUDE_FRONTEND
ARG PORT
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

COPY --from=build-${INCLUDE_FRONTEND} /app/frontend-dist /app/frontend-dist
COPY README.md /app/README.md
COPY backend/pyproject.toml backend/uv.lock /app/backend/
COPY backend/app /app/backend/app
# Resolve the exact locked dependency set from backend/uv.lock; UV_EXCLUDE repeats
# --no-emit-package for packages the slim Render target omits (empty by default).
ARG UV_EXCLUDE=
RUN pip install --no-cache-dir uv==0.12.3 \
    && cd /app/backend \
    && uv export --frozen --no-dev --no-hashes --no-install-project ${UV_EXCLUDE} -o requirements.txt \
    && pip install --no-cache-dir -r requirements.txt

WORKDIR /app/backend
# The API serves the built frontend from the copied artifact, making the container the full app.
# Render deploys with INCLUDE_FRONTEND=false and clears STATIC_DIR so the API runs headless.
ENV STATIC_DIR=/app/frontend-dist
ENV PORT=${PORT}
EXPOSE ${PORT}
CMD ["/bin/sh", "-c", "exec /usr/local/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
