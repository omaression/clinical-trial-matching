# Clinical Trial Ingestion & NLP Criteria Extraction — Design Spec

**Sub-project 1** of the Clinical Trial Matching & Eligibility Intelligence Platform.

## Context

Clinical trial eligibility criteria live in unstructured free text, making patient-trial matching slow, manual, and error-prone. This sub-project builds the data foundation: ingest oncology trials from ClinicalTrials.gov, extract structured inclusion/exclusion criteria using NLP, and store them in a canonical internal representation with FHIR export as a derived compatibility layer.

**Scope**: Backend only — FastAPI service, PostgreSQL, spaCy NLP pipeline. No frontend.

**Out of scope**: Patient profiles, matching engine, explainability, frontend UI (future sub-projects).

**MVP emphasis**: Canonical internal storage first. Auditable extraction runs. Explicit human review persistence. Deterministic ingestion/re-ingestion behavior. Extensible oncology criterion modeling. FHIR export as a derived view, not the primary storage contract.

---

## 1. Architecture

Synchronous pipeline — a single request cycle handles fetch → extract → store.

```
FastAPI Application
├── api/           REST endpoints (ingestion, retrieval, review, FHIR)
├── ingestion/     ClinicalTrials.gov V2 API client + rate limiter
├── extraction/    6-stage spaCy NLP pipeline
├── fhir/          FHIR R4 ResearchStudy mapper + Pydantic models
├── models/        SQLAlchemy ORM models
└── db/            Session management + Alembic migrations
```

### Project Structure

```
clinical-trial-matching/
├── app/
│   ├── main.py                    FastAPI app + lifespan
│   ├── config.py                  Settings (pydantic-settings)
│   ├── api/
│   │   ├── routes/
│   │   │   └── trials.py          Trial endpoints
│   │   └── dependencies.py        Shared deps (DB session, etc.)
│   ├── ingestion/
│   │   ├── ctgov_client.py        ClinicalTrials.gov V2 API client
│   │   ├── service.py             Ingestion orchestration + idempotency
│   │   └── hasher.py              Content hash for change detection
│   ├── extraction/
│   │   ├── pipeline.py            Pipeline orchestration (6 stages)
│   │   ├── section_splitter.py    Stage 1
│   │   ├── abbreviation_resolver.py  Stage 2.5
│   │   ├── entity_ruler.py        Custom EntityRuler patterns
│   │   ├── criteria_classifier.py Stage 3 (pluggable strategy)
│   │   ├── quantitative_parser.py Stage 3 sub-component
│   │   ├── negation_resolver.py   Stage 3 sub-component
│   │   └── coding/
│   │       ├── entity_coder.py    Stage 4
│   │       ├── mesh.py            MeSH term lookup
│   │       └── nci.py             NCI Thesaurus lookup
│   ├── fhir/
│   │   ├── models.py              FHIR resource Pydantic models
│   │   └── mapper.py              Trial → FHIR ResearchStudy mapper
│   ├── models/
│   │   └── database.py            SQLAlchemy models
│   └── db/
│       ├── session.py             DB session management
│       └── migrations/            Alembic migrations
├── tests/
│   ├── unit/
│   │   ├── test_section_splitter.py
│   │   ├── test_abbreviation_resolver.py
│   │   ├── test_quantitative_parser.py
│   │   ├── test_negation_resolver.py
│   │   ├── test_criteria_classifier.py
│   │   ├── test_entity_coder.py
│   │   └── test_fhir_mapper.py
│   ├── integration/
│   │   ├── test_pipeline_end_to_end.py
│   │   ├── test_ingestion_service.py
│   │   └── test_api_endpoints.py
│   ├── fixtures/
│   │   ├── sample_eligibility_texts/
│   │   ├── expected_criteria/
│   │   └── mock_ctgov_responses/
│   └── conftest.py
├── data/
│   ├── seed/                      Sample trial data
│   ├── patterns/                  EntityRuler pattern files
│   └── dictionaries/
│       └── onc_abbreviations.jsonl
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── alembic.ini
```

---

## 2. Data Model

### 2.1 `trials` — Raw ClinicalTrials.gov Data

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| nct_id | VARCHAR UNIQUE | e.g. "NCT04567890" |
| raw_json | JSONB | Full ClinicalTrials.gov API response (retained for re-extraction and audit) |
| content_hash | VARCHAR | SHA-256 of normalized eligibility-relevant fields; used for change detection on re-ingestion |
| brief_title | VARCHAR | |
| official_title | VARCHAR | |
| status | VARCHAR | "RECRUITING", "COMPLETED", etc. |
| phase | VARCHAR | "PHASE1", "PHASE2", "PHASE3", etc. |
| conditions | VARCHAR[] | e.g. {"Breast Cancer"} |
| interventions | JSONB | Drug/procedure details |
| eligibility_text | TEXT | Raw inclusion/exclusion free text |
| **Structured eligibility (from ClinicalTrials.gov)** | | Source-of-truth fields — not NLP-derived |
| eligible_min_age | VARCHAR (nullable) | e.g. "18 Years" (as provided by ClinicalTrials.gov) |
| eligible_max_age | VARCHAR (nullable) | e.g. "75 Years" |
| eligible_sex | VARCHAR (nullable) | "ALL" / "FEMALE" / "MALE" |
| accepts_healthy | BOOLEAN (nullable) | Healthy volunteers accepted |
| structured_eligibility | JSONB (nullable) | Any additional ClinicalTrials.gov structured eligibility fields |
| sponsor | VARCHAR | |
| start_date | DATE | |
| completion_date | DATE | |
| last_updated | TIMESTAMPTZ | From ClinicalTrials.gov |
| ingested_at | TIMESTAMPTZ | When we first fetched it |
| updated_at | TIMESTAMPTZ (nullable) | When re-ingested with changed content |
| extraction_status | VARCHAR | Denormalized latest state: "pending" / "completed" / "failed" |

**Precedence rules**: ClinicalTrials.gov structured values (eligible_min_age, eligible_sex, etc.) are source-of-truth when present. NLP-derived values fill gaps only. Downstream consumers check structured fields first, fall back to extracted_criteria.

**Ingestion idempotency**: Upsert keyed by `nct_id`. On re-ingestion, compare `content_hash` against stored value. If unchanged, skip. If changed, update `raw_json`, `content_hash`, `updated_at`, and trigger re-extraction. `trials.raw_json` stores only the latest ClinicalTrials.gov payload. Separately, every `pipeline_runs` row stores its own full `input_snapshot` for that run, including the initial ingestion and all later re-extractions, so every extracted result remains traceable to the exact source payload that produced it.

### 2.2 `trial_sites` — Geographic Location Data

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| trial_id | UUID FK → trials | |
| facility | VARCHAR | Site name |
| city | VARCHAR | |
| state | VARCHAR | |
| country | VARCHAR | |
| zip | VARCHAR | |
| latitude | FLOAT (nullable) | For future distance filtering |
| longitude | FLOAT (nullable) | |
| status | VARCHAR | "RECRUITING" / "NOT_YET" / "COMPLETED" / "WITHDRAWN" |

### 2.3 `pipeline_runs` — Extraction Audit Log

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | This is the `pipeline_run_id` referenced by extracted_criteria |
| trial_id | UUID FK → trials | |
| pipeline_version | VARCHAR | e.g. "0.1.0" |
| input_hash | VARCHAR | SHA-256 of the eligibility_text that was processed |
| input_snapshot | JSONB | Full ClinicalTrials.gov API response used for this specific run. Captured for every pipeline run, not only on re-ingestion, so historical runs remain auditable even after `trials.raw_json` is updated. |
| status | VARCHAR | "running" / "completed" / "failed" |
| started_at | TIMESTAMPTZ | |
| finished_at | TIMESTAMPTZ (nullable) | |
| error_message | TEXT (nullable) | Failure details |
| criteria_extracted_count | INTEGER (nullable) | |
| review_required_count | INTEGER (nullable) | |
| diff_summary | JSONB (nullable) | `{ added: N, removed: N, changed: N }` vs previous run |

Supports retries, debugging, version comparison, and operational visibility. `trials.extraction_status` is kept only as a denormalized convenience field reflecting the latest run.

### 2.4 `fhir_research_studies` — FHIR R4 Resources (Derived View)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| trial_id | UUID FK → trials | |
| resource | JSONB | Complete FHIR ResearchStudy JSON |
| version | INTEGER | Re-extraction version tracking |
| pipeline_run_id | UUID FK → pipeline_runs | Which run produced this resource |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

FHIR resources are a **derived export view**, not the canonical representation. The internal `extracted_criteria` table is the source of truth. FHIR resources are regenerated from internal data on each extraction run. This avoids forcing complex oncology logic into FHIR prematurely while preserving interoperability.

### 2.5 `extracted_criteria` — Structured Parsed Criteria (Canonical)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| trial_id | UUID FK → trials | |
| **Classification** | | |
| type | VARCHAR | "inclusion" / "exclusion" |
| category | VARCHAR | Controlled vocabulary — see category list below |
| parse_status | VARCHAR | "parsed" / "partial" / "unparsed" |
| **Original Text** | | |
| original_text | TEXT | Raw text of this criterion |
| **Value Extraction** | | |
| operator | VARCHAR | "eq" / "gte" / "lte" / "range" / "present" / "absent" / "contains" |
| value_low | FLOAT (nullable) | Numeric lower bound |
| value_high | FLOAT (nullable) | Numeric upper bound |
| value_text | VARCHAR (nullable) | Non-numeric value |
| unit | VARCHAR (nullable) | e.g. "years", "cells/L", "%" |
| raw_expression | VARCHAR (nullable) | Original quantitative text (e.g. "≥ 1.5 x 10⁹/L") for audit |
| negated | BOOLEAN | |
| **Temporal Modifiers** | | |
| timeframe_operator | VARCHAR (nullable) | "within" / "at_least" / "no_more" / "prior_to" / "since" |
| timeframe_value | FLOAT (nullable) | e.g. 28 |
| timeframe_unit | VARCHAR (nullable) | "days" / "weeks" / "months" / "years" |
| **Logic Grouping** | | |
| logic_group_id | UUID (nullable) | Shared ID for grouped criteria |
| logic_operator | VARCHAR | "AND" (default) / "OR" |
| **Coding** | | |
| coded_concepts | JSONB | Array of `{ system, code, display }` |
| **Confidence & Provenance** | | |
| confidence | FLOAT | 0.0–1.0 |
| review_required | BOOLEAN | DEFAULT false |
| review_reason | VARCHAR (nullable) | "fuzzy_match" / "uncoded_entity" / "complex_criteria" / "ambiguous_negation" / "polarity_override" |
| **Review Outcomes** | | |
| review_status | VARCHAR | "pending" / "accepted" / "corrected" / "rejected" (default: "pending" if review_required, null otherwise) |
| reviewed_by | VARCHAR (nullable) | Who resolved the review |
| reviewed_at | TIMESTAMPTZ (nullable) | |
| review_notes | TEXT (nullable) | Reviewer's notes |
| original_extracted | JSONB (nullable) | Snapshot of pre-correction values (set on "correct" action; append-only audit trail) |
| **Provenance** | | |
| pipeline_version | VARCHAR | e.g. "0.1.0" |
| pipeline_run_id | UUID FK → pipeline_runs | |
| created_at | TIMESTAMPTZ | |

**Criterion categories** (extensible controlled vocabulary):

| Category | Examples |
|----------|----------|
| age | "Age ≥ 18 years" |
| diagnosis | "Histologically confirmed breast cancer" |
| disease_stage | "Stage III or IV", "Unresectable" |
| histology | "Adenocarcinoma", "Squamous cell" |
| biomarker | "HER2-positive", "PD-L1 TPS ≥ 1%" |
| molecular_alteration | "EGFR mutation", "ALK rearrangement" |
| prior_therapy | "No prior chemotherapy within 28 days" |
| line_of_therapy | "Failed ≥1 prior line of systemic therapy" |
| lab_value | "ANC ≥ 1.5 x 10⁹/L" |
| performance_status | "ECOG 0-1" |
| organ_function | "Adequate hepatic function" |
| cns_metastases | "No active brain metastases" |
| concomitant_medication | "No concurrent CYP3A4 inhibitors" |
| other | Catch-all for criteria that don't fit above categories |

New categories can be added without schema migration — `category` is a VARCHAR, not an enum. The `other` category ensures no criterion is dropped for lack of a matching category.

**Unparsed criteria preservation**: When the pipeline cannot fully parse a criterion (too complex, ambiguous structure), the row is still created with `parse_status: "unparsed"`, `original_text` preserved, `category: "other"`, `confidence: 0.0`, and `review_required: true`. No clinically relevant text is silently dropped. Partial parses (`parse_status: "partial"`) retain whatever fields were successfully extracted alongside the full original text.

**Review audit**: When a reviewer corrects a criterion, the pre-correction field values are snapshotted into `original_extracted` (JSONB). The corrected values overwrite the main fields. This provides an append-only audit trail without a separate table. Corrected criteria become high-value evaluation data for pipeline tuning.

### 2.6 `coding_lookups` — Cached Terminology

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| system | VARCHAR | "mesh" / "nci_thesaurus" |
| code | VARCHAR | e.g. "D001943" |
| display | VARCHAR | Human-readable label |
| synonyms | VARCHAR[] | Alternate names for matching |
| parent_codes | VARCHAR[] | Hierarchy for broader matching |
| fetched_at | TIMESTAMPTZ | |
| | UNIQUE(system, code) | |

### 2.7 FHIR ResearchStudy Mapping (Derived Export)

This mapping defines how the **canonical internal representation** is projected into FHIR R4 for interoperability. FHIR is not the storage contract — it is generated from `extracted_criteria` + `trials` on demand or cached in `fhir_research_studies`.

```
FHIR ResearchStudy R4                 ←  Source
───────────────────────────────────────────────────
identifier[0].value                   ←  nct_id
title                                 ←  brief_title
status                                ←  mapped from ClinicalTrials.gov status
phase.coding[0]                       ←  mapped from ClinicalTrials.gov phase
condition[].coding[]                  ←  conditions → MeSH coded

Extension: eligibilityCriteria
├── inclusion[]                       ←  extracted_criteria (type=inclusion)
│   └── FHIR Group characteristic:
│       ├── code.coding[]             ←  coded_concepts
│       ├── valueQuantity             ←  operator + value + unit
│       ├── valueCodeableConcept      ←  value_text + coded_concepts
│       └── exclude: false
└── exclusion[]                       ←  extracted_criteria (type=exclusion)
    └── same structure, exclude: true

Criteria category → FHIR coding:
  age                → http://loinc.org|30525-0
  diagnosis          → condition.coding (MeSH)
  biomarker          → http://loinc.org|{specific LOINC}
  prior_therapy      → intervention coded (NCI)
  lab_value          → http://loinc.org|{specific LOINC}
  performance_status → http://loinc.org|89247-1 (ECOG)
  organ_function     → http://loinc.org|{organ panel}
  line_of_therapy    → NCI Thesaurus coded
```

Only criteria with `parse_status` in ("parsed", "partial") and `review_status` in ("accepted", "corrected", null) are included in the FHIR export. Corrected criteria use their reviewer-corrected values and are exported exactly like accepted criteria, because the corrected row is the canonical post-review representation. Unparsed criteria and those with `review_status: "rejected"` are excluded.

### 2.8 Indexing Strategy

| Table | Index | Type | Purpose |
|-------|-------|------|---------|
| trials | nct_id | UNIQUE B-tree | NCT ID lookup |
| trials | status | B-tree | Filter by recruiting status |
| trials | phase | B-tree | Filter by trial phase |
| trials | conditions | GIN | Array containment queries |
| trials | content_hash | B-tree | Fast change detection on re-ingestion |
| trial_sites | trial_id | B-tree | FK lookup |
| trial_sites | (country, state, city) | B-tree composite | Geographic filtering |
| extracted_criteria | trial_id | B-tree | FK lookup — most common query path |
| extracted_criteria | review_required | B-tree partial (WHERE true) | Review queue queries |
| extracted_criteria | category | B-tree | Filter by criterion type |
| extracted_criteria | pipeline_run_id | B-tree | Audit / version queries |
| extracted_criteria | coded_concepts | GIN | JSONB containment — search by coding system + code |
| pipeline_runs | trial_id | B-tree | Run history per trial |
| pipeline_runs | pipeline_version | B-tree | Version-based analysis |
| coding_lookups | (system, code) | UNIQUE B-tree | Term lookup |
| coding_lookups | synonyms | GIN | Synonym matching |

---

## 3. NLP Extraction Pipeline

6-stage spaCy + rule-based hybrid pipeline. Oncology-focused.

### Stage 1: Section Splitter

Splits raw eligibility text into individual criteria tagged inclusion/exclusion.

- **Primary**: Structural header detection ("Inclusion Criteria:", "Exclusion Criteria:")
- **Fallback**: Sentence-level polarity classification when headers are missing/malformed
  - Exclusion signals: "must not", "no history of", "excluded if", "without", negated verbs
  - Inclusion signals: "must have", "required to", positive assertions
  - Default: inclusion (when no signal detected)
- **Mixed-section handling**: When a sentence's polarity contradicts its section header, trust polarity but set `review_required: true` with `review_reason: "polarity_override"`

### Stage 2: spaCy NER

Base model: `en_core_sci_lg` (scispaCy — biomedical NER trained on CRAFT + JNLPBA + BC5CDR).

Custom EntityRuler patterns loaded from `data/patterns/`:

| Entity Type | Examples |
|-------------|----------|
| DISEASE | breast cancer, melanoma, NSCLC |
| DRUG | trastuzumab, pertuzumab, pembrolizumab |
| BIOMARKER | HER2, PD-L1, BRCA1, EGFR |
| LAB_TEST | ANC, ALT, AST, CrCl, hemoglobin |
| MEASURE | "18 years", "1.5 x 10⁹/L", "2.5× ULN" |
| PERF_SCALE | ECOG, Karnofsky |
| TIMEFRAME | "28 days", "6 months" |
| THERAPY_LINE | "first-line", "second-line", "prior line" |

### Stage 2.5: Abbreviation Resolver

Expands oncology acronyms before coding lookup to prevent valid extractions from falling into the review queue.

**Layer 1**: scispaCy `AbbreviationDetector` — detects in-document definitions (e.g., "non-small cell lung cancer (NSCLC)") and maps later uses.

**Layer 2**: Static oncology dictionary (`data/dictionaries/onc_abbreviations.jsonl`, ~200 entries) — covers common abbreviations without in-document definitions: TNBC, mCRPC, ECOG, CrCl, ULN, etc.

Output: Each entity gains an `expanded_text` field. Stage 4 uses `expanded_text` for coding lookup; original abbreviation preserved for display.

### Stage 3: Criteria Classifier

Pluggable strategy interface:

```python
class CriteriaClassifier(Protocol):
    def classify(self, criterion_text: str, entities: list[Entity]) -> ClassifiedCriterion: ...
```

**MVP implementation: `RuleBasedClassifier`**

Sub-components:

1. **QuantitativeParser** — Decomposes MEASURE spans into `operator`, `value_low`/`value_high`, `unit`, `raw_expression`. Handles scientific notation, ×ULN relative units, percentages, ranges, word operators ("at least", "no more than"). Splits compound lab refs (AST/ALT) into separate criteria with shared logic groups.

2. **NegationResolver** — Propagates negation across coordinate structures (comma-separated lists, conjunctions). "No prior treatment with Drug A, Drug B, or Drug C" negates all three. "Unless" clauses split into two logic-grouped criteria. Scope boundaries: sentence ends, contrasting conjunctions ("but", "however", "unless").

3. **TemporalParser** — Extracts washout periods and timeframes into `timeframe_operator`, `timeframe_value`, `timeframe_unit`.

4. **LogicGrouper** — Detects AND/OR relationships, assigns shared `logic_group_id`.

5. **CategoryAssigner** — Entity type + surrounding context → criterion category. Maps to the extended category vocabulary: DISEASE→diagnosis, DISEASE+stage language→disease_stage, DISEASE+histology→histology, DRUG+TIMEFRAME→prior_therapy, BIOMARKER→biomarker, molecular language→molecular_alteration, LAB_TEST+MEASURE→lab_value, PERF_SCALE+MEASURE→performance_status, "line"+ordinal→line_of_therapy, CNS/brain language→cns_metastases, concurrent medication language→concomitant_medication. Unmatched → `other`.

**Complexity routing**: Before classification, score structural complexity (multiple entity types, "unless"/"except"/"provided that", nested parentheticals, multiple conjunctions). Complex criteria → `review_required: true` with `review_reason: "complex_criteria"` in MVP. Clean upgrade path to `LLMAssistedClassifier` via the strategy interface.

**Unparsed preservation**: Criteria that cannot be parsed at all still produce a row with `parse_status: "unparsed"`, `category: "other"`, `confidence: 0.0`, `review_required: true`, and full `original_text`. Partial parses retain whatever was successfully extracted alongside the original text. No clinically relevant text is silently dropped.

### Stage 4: Entity Coder

Maps extracted entities to MeSH / NCI Thesaurus / LOINC. Uses `expanded_text` from Stage 2.5.

| Tier | Strategy | Confidence | review_required |
|------|----------|------------|-----------------|
| 1 | Exact match against `coding_lookups` | 0.95 | false |
| 2 | Synonym match (case-insensitive) | 0.85 | false |
| 3 | Fuzzy match (edit distance ≤ 2) | 0.60 | **true** |
| 4 | No match | 0.40 | **true** |

Fuzzy matches are never silently accepted — critical for clinical safety where edit distance of 1 can flip meaning (hypotension/hypertension, BRCA1/BRCA2).

Sources: DISEASE → MeSH (NLM API), DRUG → NCI Thesaurus, BIOMARKER → NCI Thesaurus, LAB_TEST → LOINC (top codes).

### Stage 5: FHIR Mapper

Assembles `extracted_criteria` rows and FHIR ResearchStudy resource (derived view). Stamps `confidence`, `pipeline_version`, `pipeline_run_id`, `parse_status`, and `review_required`/`review_reason`.

Confidence heuristic combines coding tier with classification confidence. Exact match + clean classification = 0.95. Fuzzy or complex = flagged for review.

**ClinicalTrials.gov structured field precedence**: For age, sex, and healthy-volunteer criteria, the mapper checks `trials.eligible_min_age`, `eligible_max_age`, `eligible_sex`, `accepts_healthy` first. If ClinicalTrials.gov provides these as structured data, NLP-derived values for the same fields are marked as supplementary (lower confidence, not used for matching when structured values exist).

---

## 4. API Endpoints

All routes under `/api/v1/`. Offset-based pagination (`?page=1&per_page=20`). Consistent error format: `{ "detail": "msg", "code": "NOT_FOUND" }`.

### Trial Ingestion

| Method | Path | Description |
|--------|------|-------------|
| POST | `/trials/ingest` | Ingest single trial by NCT ID. Body: `{ "nct_id": "NCT04567890" }`. Returns trial + criteria_count + review_count. |
| POST | `/trials/search-ingest` | Search ClinicalTrials.gov + ingest results. Body: `{ "condition": "breast cancer", "status": "RECRUITING", "phase": "PHASE3", "limit": 25 }`. |

### Trial Retrieval

| Method | Path | Description |
|--------|------|-------------|
| GET | `/trials` | List trials with filtering (`?status`, `?condition`, `?phase`) + pagination. |
| GET | `/trials/{trial_id}` | Single trial with criteria summary stats. |
| GET | `/trials/nct/{nct_id}` | Lookup by NCT ID. |

### Extracted Criteria

| Method | Path | Description |
|--------|------|-------------|
| GET | `/trials/{trial_id}/criteria` | All criteria for a trial. Filter: `?type`, `?category`, `?review_required`. |
| GET | `/criteria/{criterion_id}` | Single criterion with full detail. |

### FHIR

| Method | Path | Description |
|--------|------|-------------|
| GET | `/trials/{trial_id}/fhir` | FHIR R4 ResearchStudy resource. `Content-Type: application/fhir+json`. |

### Review Queue

| Method | Path | Description |
|--------|------|-------------|
| GET | `/review` | Criteria flagged for review. Filter: `?reason`, `?trial_id`. Returns items + breakdown_by_reason. |
| PATCH | `/criteria/{criterion_id}/review` | Resolve review flag. Body: `{ "action": "accept" | "correct" | "reject", "reviewed_by": "...", "review_notes": "...", "corrected_data": { ... } }`. On "correct", pre-correction values snapshotted to `original_extracted`. |

### Pipeline Management

| Method | Path | Description |
|--------|------|-------------|
| GET | `/pipeline/status` | Pipeline version + aggregate stats (total trials, criteria, review pending, failures). |
| GET | `/pipeline/runs` | List pipeline runs with filtering (`?trial_id`, `?pipeline_version`, `?status`) + pagination. |
| GET | `/pipeline/runs/{run_id}` | Single run detail with diff_summary. |
| POST | `/trials/{trial_id}/re-extract` | Re-run extraction after pipeline update. Creates new pipeline_run. Returns diff (added/removed/changed). Only triggers if content or pipeline version changed. |

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness: DB connection + spaCy model loaded. |

---

## 5. Testing Strategy

### Test Structure

- **Unit tests** — one per pipeline stage: section_splitter, abbreviation_resolver, quantitative_parser, negation_resolver, criteria_classifier, entity_coder, fhir_mapper
- **Integration tests** — full pipeline end-to-end, ingestion service (mocked HTTP), API endpoints (FastAPI TestClient), ingestion idempotency (re-ingest same/changed content), review workflow (accept/correct/reject with audit trail), pipeline_runs lifecycle
- **Fixtures** — `sample_eligibility_texts/` (real ClinicalTrials.gov text), `expected_criteria/` (gold-standard JSON), `mock_ctgov_responses/` (cached API responses)

### Gold-Standard NLP Tests

Parameterized test cases: raw eligibility text paired with expected extracted criteria JSON. Pipeline output compared field-by-field (with float tolerance for numeric values, system+code matching for coded concepts).

**10 initial fixture cases:**

1. Simple age + diagnosis (baseline)
2. Lab values with scientific notation (ANC ≥ 1.5 x 10⁹/L)
3. Washout period / temporal modifier
4. Distributed negation across drug list
5. "Unless" clause with exception
6. OR-grouped criteria (compound logic)
7. Heavy abbreviations (TNBC, mCRPC, ECOG)
8. Missing section headers (polarity fallback)
9. Line-of-therapy criteria
10. Performance status (ECOG range)
11. Unparseable complex criterion (preserved as unparsed)
12. ClinicalTrials.gov structured fields override NLP-derived age/sex
13. Disease stage + histology criteria (new categories)
14. Concomitant medication + CNS metastases (new categories)

### What Gets Mocked vs Real

- **Mocked**: ClinicalTrials.gov HTTP calls (respx), MeSH/NCI API calls (pre-populated coding_lookups)
- **Real**: PostgreSQL (testcontainers-python), spaCy pipeline (session-scoped fixture)

---

## 6. Infrastructure & Dependencies

### Docker Compose

- `app`: FastAPI + Uvicorn, hot-reload volume mounts, depends on db health
- `db`: PostgreSQL 16, persistent volume

### Core Dependencies

| Dependency | Purpose |
|------------|---------|
| FastAPI + Uvicorn | Web framework |
| SQLAlchemy 2.0 | ORM |
| Alembic | Migrations |
| Pydantic v2 | Validation / schemas |
| pydantic-settings | Configuration |
| httpx | ClinicalTrials.gov API client |
| spaCy 3.x + scispaCy | NLP pipeline |
| fhir.resources | FHIR Pydantic models |

### Dev Dependencies

| Dependency | Purpose |
|------------|---------|
| pytest + pytest-asyncio | Testing |
| respx | HTTP mocking |
| testcontainers-python | Real Postgres in tests |
| ruff | Linting + formatting |
| mypy | Type checking |
| pre-commit | Git hooks |

### Local Development

```bash
docker compose up -d db          # Start Postgres
pip install -e ".[dev]"          # Install with dev extras
alembic upgrade head             # Run migrations
uvicorn app.main:app --reload    # Start API (http://localhost:8000/docs)
pytest                           # Run all tests
python -m app.scripts.seed       # Ingest sample oncology trials
```

---

## 7. Future Sub-Projects

This spec covers sub-project 1 only. Planned follow-ups:

1. **Patient profiles + matching engine** — ingest patient data, compare against structured criteria, produce match scores
2. **Explainability layer** — generate human-readable explanations for match/no-match decisions
3. **Frontend** — Next.js dashboard for trial browsing, patient matching, review queue management
4. **Async pipeline** — Redis + Celery workers for bulk import, retry/resume
5. **Geographic matching** — leverage trial_sites for distance-based filtering
