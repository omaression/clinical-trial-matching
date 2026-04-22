# Clinical Trial Matching - Architecture

## Overview

Clinical Trial Matching is a full-stack MVP for ingesting ClinicalTrials.gov studies, extracting normalized eligibility criteria, reviewing ambiguous results, generating FHIR previews, and matching normalized patient profiles against stored trial criteria.

At a high level:

`ClinicalTrials.gov ingestion -> canonical trial + criteria extraction -> review + correction -> FHIR projection -> patient intake -> deterministic matching`

## Runtime Components

### Backend

- **Framework:** FastAPI (`app/main.py`)
- **Configuration:** Pydantic settings in `app/config.py`
- **Persistence:** SQLAlchemy models in `app/models/database.py`, session setup in `app/db/session.py`, Alembic migrations in `app/db/migrations/`
- **Primary API surface:** route modules under `app/api/routes/`

### Frontend

- **Framework:** Next.js App Router in `frontend/src/app/`
- **API access:** server-side client in `frontend/src/lib/api/client.ts`
- **Shell/components:** reusable UI in `frontend/src/components/`

### Local infrastructure

- `docker-compose.yml` defines `db`, `app`, and `frontend` services for local full-stack runs.
- `scripts/dev.sh` starts the backend and frontend locally, runs migrations, and syncs coding lookups unless explicitly skipped.
- Personal compose override files can be kept locally, but they are not part of the committed project surface.

## Backend Module Map

| Path | Purpose | Notable files |
|------|---------|---------------|
| `app/api/` | FastAPI routing, schemas, dependencies, errors, OpenAPI helpers | `routes/trials.py`, `routes/patients.py`, `schemas.py`, `dependencies.py` |
| `app/ingestion/` | ClinicalTrials.gov fetch + normalization pipeline inputs | `ctgov_client.py`, `service.py`, `hasher.py` |
| `app/extraction/` | Eligibility parsing, classification, decomposition, coding helpers | `pipeline.py`, `criteria_classifier.py`, `section_splitter.py`, `coding/` |
| `app/fhir/` | Trial-level and criterion-level FHIR projection | `mapper.py`, `criterion_projection.py`, `models.py` |
| `app/matching/` | Deterministic patient-to-trial matching | `service.py` |
| `app/models/` | ORM models for persisted application state | `database.py` |
| `app/db/` | DB session and Alembic migration environment | `session.py`, `migrations/` |
| `app/scripts/` | Local/admin scripts for seed and verification workflows | `seed.py`, `seed_demo.py`, `curated_corpus_report.py` |

## Current Frontend Route Surface

The committed frontend currently exposes these route entrypoints:

- `/` - operations console landing page
- `/pipeline` - ingestion and pipeline status
- `/trials` - trial list/search
- `/trials/[trialId]` - trial detail, criteria, and FHIR views
- `/review` - review queue
- `/patients` - patient list/create flow
- `/patients/[patientId]` - patient detail and matching actions
- `/matches/[matchId]` - persisted match result detail

## Extraction and Matching Flow

1. **Ingest** trial records from ClinicalTrials.gov.
2. **Store** source trial payloads and latest-run-aware pipeline history.
3. **Extract** normalized criteria from free-text eligibility content.
4. **Review** ambiguous or blocked criteria through the review queue.
5. **Project** the latest canonical trial state into FHIR outputs where policy allows.
6. **Create/update** normalized patient records.
7. **Match** patients against stored criteria and persist match explanations.

## Repository Shape

```text
clinical-trial-matching/
├── app/                    # FastAPI backend, extraction, FHIR, matching, DB
├── data/                   # Dictionaries, patterns, terminology seed data
├── frontend/               # Next.js frontend
├── scripts/                # Local developer scripts
├── docker-compose.yml      # Committed local stack definition
├── render.yaml             # Deployment blueprint for backend/database
├── .env.example            # Documented environment examples
├── README.md               # Project overview and setup
└── ARCHITECTURE.md         # This file
```
