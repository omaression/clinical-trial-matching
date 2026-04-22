# Clinical Trial Matching

Clinical Trial Matching is an MVP for turning ClinicalTrials.gov study records into a usable matching workflow:

- ingest and normalize trial records from ClinicalTrials.gov
- extract canonical eligibility criteria from unstructured eligibility text
- flag ambiguous criteria for human review
- derive a FHIR `ResearchStudy` preview from the latest canonical trial state
- project grounded medication criteria into criterion-level FHIR `MedicationStatement` resources
- create normalized patient profiles
- run deterministic patient-to-trial matching with stored explanations and evidence payloads

The current product surface is a FastAPI backend plus a Next.js operations console.

## Current State

The current MVP demonstrates the full operational path:

1. Trial ingestion from ClinicalTrials.gov
2. Multi-stage deterministic extraction into canonical criteria with provenance and confidence
3. Latest-run-aware review queue and correction workflow
4. Trial-level FHIR `ResearchStudy` export plus criterion-level medication projections when terminology is safely grounded
5. Normalized patient intake
6. Deterministic matching with persisted match results and explanations

The frontend is intended to make that path demoable end to end from one console.

## Implemented So Far

- Ingestion and re-extraction are latest-run-aware, with append-only pipeline history and canonical stored criteria.
- Extraction now handles atomic clause splitting, grouped logic, medication exception semantics, assay/specimen context, and therapy-history decomposition.
- Terminology resolution is stricter and safer: bad fuzzy mappings were removed, grounded concepts are favored, and unresolved therapy classes stay blocked instead of being guessed.
- Internal-only eligibility semantics now cover administrative, behavioral, reproductive, and device-related constraints for matching and review.
- The backend exposes both trial-level FHIR `ResearchStudy` output and criterion-level medication FHIR projections for safely grounded medication criteria.
- Patient intake, matching, and persisted explanation payloads are implemented end to end.
- The frontend console supports ingest, review, trials, patients, matches, and inspection of structured/FHIR outputs.
- The stack is containerized and prepared for a Render backend plus Vercel frontend deployment.

## Recent Extraction and FHIR Improvements

- Timeframes are attached to the correct medication or therapy exposure clause instead of drifting onto nearby diagnoses.
- Prior-therapy and line-of-therapy sentences now decompose into atomic therapy-history clauses with preserved AND/OR semantics.
- Medication projection is now high-precision:
  - named drugs project through RxNorm
  - safe therapy or medication classes project through source-backed NCIt concepts
  - unresolved or unsafe classes stay blocked rather than being forced into codes
- Explicit combination exposures such as `trastuzumab + chemotherapy` are projected as separate medication resources instead of a fabricated combination code.
- Internal-only categories such as `administrative_requirement`, `behavioral_constraint`, `device_constraint`, and `reproductive_status` remain visible for review and matching, but are intentionally excluded from FHIR by policy.
- A curated corpus verification harness now tracks review counts, projection counts, blocked terminology cases, and category distribution across representative fixtures.

## Tech Stack

- Backend: FastAPI, SQLAlchemy, Alembic, PostgreSQL
- NLP: spaCy, SciSpaCy, rule-based extraction and coding
- Frontend: Next.js App Router, TypeScript, Tailwind CSS
- Containers: Docker, Docker Compose
- Deployment target: Render for API/Postgres, Vercel for frontend

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker Desktop or a local PostgreSQL instance
- `uv`, `npm`, `curl`, and `lsof` available in `PATH`

### Quick Start (Recommended)

This path matches the setup verified in this repo: install CPython 3.12 with `uv`, create a repo-local virtualenv, install the backend in editable mode, install frontend dependencies, then run the launcher.

1. Copy environment templates:

   ```bash
   cp .env.example .env
   cp frontend/.env.example frontend/.env.local
   ```

2. Start Postgres:

   ```bash
   docker compose up -d db
   ```

3. Install backend dependencies:

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

5. Start the dev server:

   ```bash
   ./scripts/dev.sh
   ```

   The startup path syncs the coding lookup catalog automatically, so local runs use the current terminology seed.

**Default local URLs:**
- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/api/v1/health`

### Manual Local Startup

Use this when you want explicit control over each process.

1. Copy environment templates:

   ```bash
   cp .env.example .env
   cp frontend/.env.example frontend/.env.local
   ```

2. Start Postgres:

   ```bash
   docker compose up -d db
   ```

3. Create a Python environment and install dependencies:

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

5. Start the backend (in one terminal):

   ```bash
   export CTM_API_KEY=***  # from your .env
   uvicorn app.main:app --reload
   ```

6. Start the frontend (in another terminal):

   ```bash
   cd frontend
   npm install
   export CTM_FRONTEND_API_BASE_URL=http://127.0.0.1:8000/api/v1
   export CTM_FRONTEND_API_KEY=***  # from frontend/.env.local
   npm run dev
   ```

7. Optional demo seed:

   ```bash
   python -m app.scripts.seed_demo
   ```

## Full-Stack Containers

You can run the full application stack in containers:

```bash
docker compose up --build
```

This starts:
- `db` on port `5432`
- `app` on port `8000`
- `frontend` on port `3000`

Verify the backend is healthy after startup:

```bash
curl -fsS http://localhost:8000/api/v1/health
```

> **Note:** Personal `docker-compose.override.yml` files are ignored by `.gitignore`. Keep custom overrides local only.

## Demo Flow

The clean MVP walkthrough is:

1. Seed local demo data with `python -m app.scripts.seed_demo`
2. Open `Pipeline` and ingest a trial or search-ingest a small batch
3. Open a trial detail page and inspect:
   - structured trial fields
   - extracted criteria
   - trial-level FHIR `ResearchStudy` preview
   - criterion-level medication FHIR projections when grounded
4. Open `Review` and resolve review-required criteria
5. Open `Patients`, create or inspect a patient
6. Run matching and open the persisted match result page

**Key frontend routes:**
- `/`
- `/pipeline`
- `/trials`
- `/review`
- `/patients`

## Deployment

One supported deployment pattern is:
- frontend on Vercel from `frontend/`
- backend on Render from the repo root Dockerfile
- managed Postgres for the application database

**Example frontend env vars:**
- `CTM_FRONTEND_API_BASE_URL=https://api.example.com/api/v1`
- `CTM_FRONTEND_API_KEY=***`

**Example backend env vars:**
- `CTM_DATABASE_URL`
- `CTM_API_KEY`
- `CTM_RUN_MIGRATIONS=1`

There is also a `render.yaml` blueprint in the repo for the backend/database side if you want to use Render.

## Roadmap

The following items represent the prioritized next phase of development. These are tracked as issues in the repository and refined as requirements before implementation.

| Priority | Item | Description |
|----------|------|-------------|
| 1 | Terminology gaps | Source safe parent/class concepts for remaining blocked therapy classes |
| 2 | Corpus validation | Expand beyond sentinel trials; track review residue, blocked terminology, and projection counts |
| 3 | Product polish | Async/batch ingestion, geographic/site-aware matching, public deployment hardening |
| 4 | Interoperability | Decide if internal-only eligibility categories need formal FHIR design |

> **Note:** The MVP is complete and functional. The roadmap focuses on production-readiness and coverage expansion.

## Verification

Use the following commands to verify a local setup:

- **backend tests:** `pytest -q`
- **frontend typecheck:** `cd frontend && npm run typecheck`
- **frontend build:** `cd frontend && npm run build`
- **full stack runtime:** `docker compose up --build -d`
- **backend health:** `curl -fsS http://127.0.0.1:8000/api/v1/health`
- **curated corpus report:**

  ```bash
  ./.ctm-dev/bin/python -m app.scripts.curated_corpus_report
  ./.ctm-dev/bin/python -m app.scripts.curated_corpus_report --format json
  ```
