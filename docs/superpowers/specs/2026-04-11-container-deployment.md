# Container and Deployment Guide

This repository now supports two deployment modes:

1. Full-stack containers for local smoke tests or non-Vercel self-hosting
2. Split deployment with Render for the backend API and Vercel for the Next.js frontend

## Images

### Backend API

- Dockerfile: `./Dockerfile`
- Default port: `8000`
- Entry script: `./scripts/container-start-backend.sh`

Runtime environment variables:

- `CTM_DATABASE_URL` required for real deployments
- `CTM_API_KEY` required for protected operations
- `CTM_RUN_MIGRATIONS=1` to run Alembic before API startup
- `PORT` defaults to `8000`
- `WEB_CONCURRENCY` defaults to `1`

### Frontend

- Dockerfile: `./frontend/Dockerfile`
- Default port: `3000`
- Entry script: `./frontend/scripts/container-start.sh`

Runtime environment variables:

- `CTM_FRONTEND_API_BASE_URL` required
- `CTM_FRONTEND_API_KEY` required for protected server-side operations
- `PORT` defaults to `3000`

The frontend reads these values server-side at runtime. They do not need to be baked into the image at build time.

## Local full-stack containers

Start the full stack:

```bash
docker compose up --build
```

Services:

- Frontend: `http://127.0.0.1:3000`
- Backend API: `http://127.0.0.1:8000`
- Backend health: `http://127.0.0.1:8000/api/v1/health`
- Postgres: `localhost:5432`

The compose stack uses:

- `CTM_DATABASE_URL=postgresql://ctm:ctm@db:5432/clinical_trials`
- `CTM_API_KEY=local-dev-api-key` unless overridden
- `CTM_RUN_MIGRATIONS=1` on backend startup
- `CTM_FRONTEND_API_BASE_URL=http://app:8000/api/v1` inside the frontend container

If you only need Postgres for local non-container development:

```bash
docker compose up -d db
```

## Render backend

`render.yaml` defines a Docker-based web service and a Render Postgres database.

Recommended Render shape:

- Render web service for the FastAPI backend using the root `Dockerfile`
- Render Postgres for `clinical_trials`
- Health check path: `/api/v1/health`

Required backend environment variables:

- `CTM_DATABASE_URL` from the Render Postgres connection string
- `CTM_API_KEY` set manually in Render
- `CTM_RUN_MIGRATIONS=1`

If you later scale the API beyond a single instance, move migrations out of startup and into a dedicated pre-deploy step.

## Vercel frontend

Deploy the `frontend/` directory as the Vercel project root.

Required Vercel environment variables:

- `CTM_FRONTEND_API_BASE_URL=https://api.ctm.omaression.com/api/v1`
- `CTM_FRONTEND_API_KEY=<same value as Render CTM_API_KEY>`

`CTM_FRONTEND_API_KEY` must stay server-only. Do not expose it through `NEXT_PUBLIC_*`.

Recommended domain split:

- `ctm.omaression.com` -> Vercel frontend
- `api.ctm.omaression.com` -> Render backend

The frontend performs its API calls from the server runtime, so it can safely hold the backend API key as a normal Vercel environment variable.

## Build commands

Backend image:

```bash
docker build -t ctm-api .
docker run --rm -p 8000:8000 \
  -e CTM_DATABASE_URL=postgresql://ctm:ctm@host.docker.internal:5432/clinical_trials \
  -e CTM_API_KEY=local-dev-api-key \
  -e CTM_RUN_MIGRATIONS=1 \
  ctm-api
```

Frontend image:

```bash
docker build -t ctm-frontend ./frontend
docker run --rm -p 3000:3000 \
  -e CTM_FRONTEND_API_BASE_URL=http://host.docker.internal:8000/api/v1 \
  -e CTM_FRONTEND_API_KEY=local-dev-api-key \
  ctm-frontend
```
