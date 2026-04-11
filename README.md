# Clinical Trial Matching

Clinical Trial Matching is an MVP for turning ClinicalTrials.gov study records into a usable matching workflow:

- ingest and normalize trial records from ClinicalTrials.gov
- extract canonical eligibility criteria from unstructured eligibility text
- flag ambiguous criteria for human review
- derive a FHIR `ResearchStudy` preview from the latest canonical trial state
- create normalized patient profiles
- run deterministic patient-to-trial matching with stored explanations and evidence payloads

The current product surface is a FastAPI backend plus a Next.js operations console.

## MVP Scope

The MVP demonstrates the full core path:

1. Trial ingestion from ClinicalTrials.gov
2. Multi-stage rule-based NLP extraction into canonical criteria
3. Latest-run-aware review queue and correction workflow
4. FHIR export from canonical trial data
5. Normalized patient intake
6. Deterministic matching with persisted match results and explanations

The frontend is intended to make that path demoable end to end from one console.

## Tech Stack

- Backend: FastAPI, SQLAlchemy, Alembic, PostgreSQL
- NLP: spaCy, SciSpaCy, rule-based extraction and coding
- Frontend: Next.js App Router, TypeScript, Tailwind CSS
- Containers: Docker, Docker Compose
- Deployment target: Render for API/Postgres, Vercel for frontend

## Development Setup

### Prerequisites

- Python 3.12
- Node.js 20+
- Docker Desktop or a local PostgreSQL instance
- `npm` available in `PATH`

### Option A: One-command local startup

This is the cleanest local path once dependencies are installed.

1. Start Postgres:

```bash
docker compose up -d db
```

2. Create or activate a Python environment and install backend dependencies:

```bash
conda create -p ./.ctm-dev python=3.12 -y
conda activate ./.ctm-dev
pip install -e ".[dev]"
```

3. Install frontend dependencies:

```bash
cd frontend && npm install && cd ..
```

4. Start the stack:

```bash
./scripts/dev.sh
```

Default local URLs:

- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/api/v1/health`

Optional demo data:

```bash
python -m app.scripts.seed_demo
```

### Option B: Manual local startup

Use this when you want explicit control over each process.

1. Start Postgres:

```bash
docker compose up -d db
```

2. Create or activate a Python environment and install dependencies:

```bash
conda create -p ./.ctm-dev python=3.12 -y
conda activate ./.ctm-dev
pip install -e ".[dev]"
```

3. Run migrations:

```bash
alembic upgrade head
```

4. Start the backend:

```bash
export CTM_API_KEY=local-dev-api-key
uvicorn app.main:app --reload
```

5. In a second terminal, start the frontend:

```bash
cd frontend
npm install
export CTM_FRONTEND_API_BASE_URL=http://127.0.0.1:8000/api/v1
export CTM_FRONTEND_API_KEY=local-dev-api-key
npm run dev
```

6. Optional demo seed:

```bash
python -m app.scripts.seed_demo
```

## Full-Stack Containers

You can run the full application stack in containers:

```bash
docker compose up --build
```

This starts:

- `db` on `5432`
- `app` on `8000`
- `frontend` on `3000`

Container runtime has been verified locally.

## Demo Flow

The clean MVP walkthrough is:

1. Seed local demo data with `python -m app.scripts.seed_demo`
2. Open `Pipeline` and ingest a trial or search-ingest a small batch
3. Open a trial detail page and inspect:
   - structured trial fields
   - extracted criteria
   - FHIR preview
4. Open `Review` and resolve review-required criteria
5. Open `Patients`, create or inspect a patient
6. Run matching and open the persisted match result page

Key frontend routes:

- `/`
- `/pipeline`
- `/trials`
- `/review`
- `/patients`

## Deployment

The intended deployment split is:

- `ctm.omaression.com` -> Vercel frontend from `frontend/`
- `api.ctm.omaression.com` -> Render backend from the repo root Dockerfile
- Render Postgres -> `clinical_trials`

Required Vercel env vars:

- `CTM_FRONTEND_API_BASE_URL=https://api.ctm.omaression.com/api/v1`
- `CTM_FRONTEND_API_KEY=<same value as Render CTM_API_KEY>`

Required Render env vars:

- `CTM_DATABASE_URL`
- `CTM_API_KEY`
- `CTM_RUN_MIGRATIONS=1`

There is also a `render.yaml` blueprint in the repo for the backend/database side.

## Development Stages

The work so far has progressed through these stages:

1. Ingestion and re-ingestion hardening
2. Append-only pipeline history and latest-run-aware reads
3. Review workflow hardening and audit-safe canonical storage
4. NLP fixture expansion and extraction accuracy improvements
5. Deterministic coding and criterion-level review aggregation
6. Patient data model, matching engine, and explanation persistence
7. Frontend operations console for ingest, review, trials, patients, and matches
8. Containerization and deployment preparation for Render + Vercel

## Next Steps

The MVP is demonstrable now, but the highest-value remaining work is still clear:

- broaden real ClinicalTrials.gov fixture coverage for more edge-case eligibility language
- improve the remaining genuinely ambiguous extraction residue
- add async bulk ingestion and job status tracking
- add geographic/site-aware matching
- tighten release/deployment polish for public portfolio presentation

## Verification

Recent verification performed in this repository includes:

- backend tests via `pytest`
- frontend `npm run typecheck`
- frontend `npm run build`
- backend Docker build
- frontend Docker build
- `docker compose up --build -d` runtime verification
