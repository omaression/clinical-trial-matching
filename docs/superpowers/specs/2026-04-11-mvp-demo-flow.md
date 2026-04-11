# MVP Demo Flow

This repository now supports a complete MVP walkthrough from the frontend console.

## Before the Demo

1. Start PostgreSQL:

```bash
docker compose up -d db
```

2. Install backend and frontend dependencies if they are not already installed.

3. Recommended local demo seed after the stack is available:

```bash
python -m app.scripts.seed_demo
```

This loads:

- one mock ClinicalTrials.gov-backed breast cancer trial
- one synthetic review-heavy trial
- two synthetic patients
- persisted match results for those patients

4. Start the local stack:

```bash
./scripts/dev.sh
```

Open the frontend at `http://127.0.0.1:3000`.

## End-to-End Walkthrough

### 1. Ingest trials

Go to `Pipeline`.

- For the cleanest demo, use `Single Trial Ingest` with a known NCT ID such as `NCT05346328`.
- To show batch behavior, use `Search and Ingest Batch` with a small limit such as:
  - condition: `non-small cell lung cancer`
  - status: `RECRUITING`
  - limit: `5`

This demonstrates:

- protected operational writes
- ClinicalTrials.gov fetch and persistence
- pipeline run creation
- canonical criteria extraction

### 2. Inspect extraction output

Open the ingested trial from `Pipeline` or `Trials`.

Show:

- source-structured eligibility fields
- raw eligibility narrative
- latest extracted criteria
- derived FHIR preview

This demonstrates:

- latest-run-aware trial reads
- canonical internal representation
- FHIR export as a derived view

### 3. Resolve review-required criteria

Open `Review`.

If items are present, accept, reject, or correct one row. If the queue is empty, explain that the current latest-run set did not produce review-required criteria and ingest another trial or batch to exercise the workflow.

This demonstrates:

- human-in-the-loop review
- persisted review state
- latest-run review queue semantics

### 4. Create a patient

Open `Patients` and create a patient profile with a few facts:

- external ID
- sex
- birth date
- one or more conditions
- biomarkers or medications when relevant

This demonstrates:

- normalized patient storage
- protected write flow through the frontend

### 5. Run matching

Open the patient detail page and click `Run matching`.

Then open the resulting match detail page.

Show:

- trial-level status
- score
- blockers and unknowns
- per-criterion explanations
- evidence payloads

This demonstrates:

- deterministic patient-trial evaluation
- latest-run-only matching
- stored explainability output

## Short Demo Narrative

If you need a concise spoken walkthrough:

1. Ingest a trial or small trial batch from ClinicalTrials.gov
2. Show how the system stores the source payload, extracts canonical criteria, and derives FHIR
3. Resolve anything that needs human review
4. Create a patient profile
5. Run matching and inspect the explanation trail for why a trial is eligible, possible, or ineligible
