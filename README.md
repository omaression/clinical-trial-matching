# Clinical Trial Matching

Clinical Trial Matching is an MVP for turning ClinicalTrials.gov study records into a usable trial-operations and patient-matching workflow.

It supports an end-to-end operational path:
- ingest and normalize ClinicalTrials.gov studies
- extract canonical eligibility criteria from free-text eligibility narratives
- surface ambiguous criteria for human review
- export the latest canonical trial state as FHIR `ResearchStudy`
- project safely grounded medication criteria into criterion-level FHIR `MedicationStatement` resources
- create normalized patient profiles
- run deterministic patient-to-trial matching with stored explanations and evidence payloads

The product surface is a FastAPI backend plus a Next.js operations console.

## MVP Status

The MVP is functional and demoable end to end.

Current capabilities include:
1. Trial ingestion from ClinicalTrials.gov
2. Latest-run-aware extraction into canonical criteria with provenance and confidence
3. Review queue workflows for unresolved or ambiguous criteria
4. Trial-level FHIR `ResearchStudy` export and criterion-level medication projection when terminology grounding is safe
5. Normalized patient intake
6. Deterministic patient matching with persisted results and explanation payloads

## Recent Improvements

Recent work in this release cycle focused on precision, safety, and operator clarity:

- **Safer terminology and projection behavior**
  - grounded concepts are favored over fuzzy guesses
  - unresolved therapy classes stay blocked instead of being forced into unsafe codes
  - explicit combination exposures project as separate medication resources instead of fabricated combination concepts

- **Better extraction quality**
  - medication and therapy timeframes attach to the correct clause
  - therapy-history and line-of-therapy text decompose into more atomic criteria
  - a curated corpus harness tracks review counts, projection counts, blocked terminology cases, and category coverage
  - targeted residue reduction improved decomposition for a representative stage-plus-biomarker oncology pattern

- **Cleaner operational UX**
  - patient intake now handles blank optional form fields safely instead of crashing on invalid raw form values
  - search-ingest now uses a CT.gov-compatible phase filter path and returns clearer request-level errors
  - provisional match results now separate **Determinate fit** from **Coverage** so partially evaluated matches are harder to misread

## Tech Stack

- **Backend:** FastAPI, SQLAlchemy, Alembic, PostgreSQL
- **NLP / extraction:** spaCy, SciSpaCy, rule-based extraction and coding
- **Frontend:** Next.js App Router, TypeScript, Tailwind CSS
- **Containers:** Docker, Docker Compose
- **Deployment target:** Render (backend/Postgres), Vercel (frontend)

## Repository Layout

```text
app/                FastAPI app, extraction pipeline, matching, FHIR mapping
frontend/           Next.js operations console
tests/              Backend unit and integration coverage
scripts/            Local developer helpers, including full-stack launcher
data/               Dictionaries, patterns, and local extraction assets
alembic/            Database migrations
```

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker Desktop or a local PostgreSQL instance
- `uv`, `npm`, `curl`, and `lsof` available in `PATH`

## Quick Start (Recommended)

This is the verified local path for running the full stack in development.

1. Copy environment templates:

   ```bash
   cp .env.example .env
   cp frontend/.env.example frontend/.env.local
   ```

2. Start Postgres:

   ```bash
   docker compose up -d db
   ```

3. Install backend dependencies into a repo-local Python 3.12 environment:

   ```bash
   uv python install 3.12
   uv venv --python 3.12 .ctm-dev
   uv pip install --python .ctm-dev/bin/python -e ".[dev]"
   export PATH="$PWD/.ctm-dev/bin:$PATH"
   ```

4. Install frontend dependencies:

   ```bash
   cd frontend && npm install && cd ..
   ```

5. Start the development stack:

   ```bash
   ./scripts/dev.sh
   ```

   The launcher will:
   - run migrations
   - sync coding lookup seed data
   - start the backend
   - start the frontend

### Default Local URLs

- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/api/v1/health`

## Manual Local Startup

Use this path if you want explicit control over each process.

1. Copy environment templates:

   ```bash
   cp .env.example .env
   cp frontend/.env.example frontend/.env.local
   ```

2. Start Postgres:

   ```bash
   docker compose up -d db
   ```

3. Create the Python environment and install backend dependencies:

   ```bash
   uv python install 3.12
   uv venv --python 3.12 .ctm-dev
   uv pip install --python .ctm-dev/bin/python -e ".[dev]"
   export PATH="$PWD/.ctm-dev/bin:$PATH"
   ```

4. Run migrations:

   ```bash
   alembic upgrade head
   ```

5. Start the backend:

   ```bash
   export CTM_API_KEY=***
   uvicorn app.main:app --reload
   ```

6. Start the frontend in another terminal:

   ```bash
   cd frontend
   npm install
   export CTM_FRONTEND_API_BASE_URL=http://127.0.0.1:8000/api/v1
   export CTM_FRONTEND_API_KEY=***
   npm run dev
   ```

7. Optional demo seed:

   ```bash
   python -m app.scripts.seed_demo
   ```

## Full-Stack Containers

You can also run the full application stack in containers:

```bash
docker compose up --build
```

This starts:
- `db` on port `5432`
- `app` on port `8000`
- `frontend` on port `3000`

Verify backend health after startup:

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health
```

> Personal `docker-compose.override.yml` files are ignored by `.gitignore`; keep custom overrides local only.

## Demo Flow

A clean MVP walkthrough is:

1. Seed local demo data with `python -m app.scripts.seed_demo` (optional)
2. Open **Pipeline** and ingest one trial or a small search-ingest batch
3. Open a trial detail page and inspect:
   - structured trial fields
   - extracted criteria
   - trial-level FHIR `ResearchStudy` preview
   - criterion-level medication FHIR projections when grounded
4. Open **Review** and resolve review-required criteria
5. Open **Patients**, create a patient profile, and inspect the normalized record
6. Run matching and open the persisted result page

### Key Frontend Routes

- `/`
- `/pipeline`
- `/trials`
- `/review`
- `/patients`
- `/matches/[matchId]`

## Verification

Use the following commands to verify a local setup:

- **backend tests**

  ```bash
  pytest -q
  ```

- **frontend typecheck**

  ```bash
  cd frontend && npm run typecheck
  ```

- **frontend build**

  ```bash
  cd frontend && npm run build
  ```

- **full stack runtime**

  ```bash
  docker compose up --build -d
  ```

- **backend health**

  ```bash
  curl -fsS http://127.0.0.1:8000/api/v1/health
  ```

- **curated corpus report**

  ```bash
  ./.ctm-dev/bin/python -m app.scripts.curated_corpus_report
  ./.ctm-dev/bin/python -m app.scripts.curated_corpus_report --format json
  ```

## Deployment

One supported deployment pattern is:
- frontend on Vercel from `frontend/`
- backend on Render from the repo root Dockerfile
- managed Postgres for the application database

### Example Frontend Environment Variables

- `CTM_FRONTEND_API_BASE_URL=https://api.example.com/api/v1`
- `CTM_FRONTEND_API_KEY=***`

### Example Backend Environment Variables

- `CTM_DATABASE_URL`
- `CTM_API_KEY`
- `CTM_RUN_MIGRATIONS=1`

A `render.yaml` blueprint is included for the backend/database side if you want to use Render.

## Roadmap

The next phase of work focuses on production-readiness and coverage expansion.

| Priority | Item | Description |
|----------|------|-------------|
| 1 | Terminology gaps | Source safe parent/class concepts for remaining blocked therapy classes |
| 2 | Corpus validation | Expand beyond sentinel trials; keep tracking review residue, blocked terminology, and projection counts |
| 3 | Product polish | Async/batch ingestion, geographic/site-aware matching, and public deployment hardening |
| 4 | Interoperability | Decide whether internal-only eligibility categories need a formal FHIR design |

## Notes

- Internal-only categories such as administrative, behavioral, device, and reproductive constraints remain visible for review and matching, but are intentionally excluded from FHIR by policy.
- The MVP is complete enough to demonstrate the full ingest → review → patient → match workflow from a single console.
