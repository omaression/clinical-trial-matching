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

The startup path now syncs the coding lookup catalog automatically, so local runs use the current terminology seed without requiring a separate manual seed step for lookups.

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
   - trial-level FHIR `ResearchStudy` preview
   - criterion-level medication FHIR projections when grounded
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

## Next Steps

The remaining roadmap is now narrower and more concrete:

- Terminology and projection gaps:
  - source safe parent or class concepts for the remaining blocked therapy classes where authoritative concepts exist
  - improve the remaining genuinely complex medication-exception and washout logic that still deserves review
  - continue increasing standard FHIR projection coverage without relaxing the current precision policy
- Corpus-scale validation:
  - broaden real ClinicalTrials.gov study coverage beyond the current sentinel trials and curated fixture sweep
  - keep tracking review-required residue, blocked terminology cases, and projection counts as the corpus expands
  - verify that extraction gains generalize across more oncology and medication-heavy studies
- Product and deployment polish:
  - add async/batch ingestion and operational job status handling
  - add geographic/site-aware matching
  - harden the public deployment and demo presentation for `ctm.omaression.com`
  - decide whether any internal-only eligibility categories should ever receive a formal interoperability design

## Verification

Recent verification performed in this repository includes:

- full backend test suite via `pytest`
- frontend `npm run typecheck`
- frontend `npm run build`
- backend Docker build
- frontend Docker build
- `docker compose up --build -d` runtime verification
- curated corpus verification via:

```bash
./.ctm-dev/bin/python -m app.scripts.curated_corpus_report
./.ctm-dev/bin/python -m app.scripts.curated_corpus_report --format json
```
