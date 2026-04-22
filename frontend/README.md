# Clinical Trial Matching Frontend

This frontend is the Next.js operations console for the Clinical Trial Matching MVP.

## Prerequisites

- Node.js 20+
- A reachable backend API
- `npm` available in `PATH`

## Local setup

From `frontend/`:

```bash
npm install
```

Create `frontend/.env.local` with:

```bash
CTM_FRONTEND_API_BASE_URL=http://127.0.0.1:8000/api/v1
CTM_FRONTEND_API_KEY=local-dev-api-key
```

The repo root `.env.example` documents both backend/root variables and the frontend variables you should copy into `frontend/.env.local`.

## Development commands

```bash
npm run dev
npm run build
npm run start
npm run lint
npm run typecheck
npm run generate:openapi
```

## Current route map

- `/` - console landing page
- `/pipeline` - ingest trials and inspect pipeline status/runs
- `/trials` - trial list/search
- `/trials/[trialId]` - trial detail, criteria, and FHIR views
- `/review` - review queue and correction flow
- `/patients` - patient list/create flow
- `/patients/[patientId]` - patient detail and match actions
- `/matches/[matchId]` - persisted match result detail

## Current source layout

```text
frontend/
├── src/app/         # App Router pages, layouts, and server actions
├── src/components/  # Reusable UI components
├── src/lib/         # API client, config, shared helpers, types
└── scripts/         # Frontend support scripts
```

## API integration notes

- The frontend uses server-side fetches through `src/lib/api/client.ts`.
- `CTM_FRONTEND_API_BASE_URL` is required.
- `CTM_FRONTEND_API_KEY` is only required for protected operations; when present it is sent as `X-API-Key`.

## Stack

- Next.js 15 App Router
- React 19
- TypeScript
- Tailwind CSS
