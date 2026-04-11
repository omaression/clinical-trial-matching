# Clinical Trial Ingestion & NLP Criteria Extraction - Spec Recommendations

**Review date:** 2026-04-09  
**Spec under review:** `docs/superpowers/specs/2026-04-09-trial-ingestion-extraction-design.md`

## Overall Assessment

The design is solid for an MVP: the system boundary is clear, the pipeline is concrete, and the data model is already close to implementation. The main gaps are around auditability, review workflow persistence, ingestion update semantics, and keeping the MVP storage model practical instead of over-optimizing for FHIR too early.

## Recommended Spec Changes

### 1. Persist ClinicalTrials.gov structured eligibility fields separately from free text

ClinicalTrials.gov already provides structured eligibility attributes such as age, sex, and healthy-volunteer status. These should be stored as source-of-truth fields on the trial record rather than forcing NLP to recover them from `eligibility_text`.

**Recommendation**

- Add explicit columns or a dedicated JSONB subdocument for source eligibility fields.
- Use extracted criteria to augment these fields, not replace them.
- Document precedence rules: ClinicalTrials.gov structured values win when present; NLP-derived values fill gaps only.

**Why**

- Reduces avoidable extraction errors.
- Preserves source fidelity.
- Simplifies downstream matching for common filters.

### 2. Add a `pipeline_runs` extraction audit table

`trials.extraction_status` is too coarse to support retries, debugging, version comparisons, or operational visibility.

**Recommendation**

Add a `pipeline_runs` table with fields such as:

- `id`
- `trial_id`
- `pipeline_version`
- `input_hash`
- `status`
- `started_at`
- `finished_at`
- `error_message`
- `criteria_extracted_count`
- `review_required_count`
- `diff_summary` or equivalent change metadata

Keep `trials.extraction_status` only as a denormalized latest-state field if needed for API convenience.

**Why**

- Makes re-extraction and failure handling tractable.
- Supports auditing and regression analysis across pipeline versions.
- Gives reviewers and operators visibility into what changed and why.

### 3. Persist human review outcomes explicitly

The spec includes review endpoints, but the schema does not yet show where review decisions are stored.

**Recommendation**

Add review state to extracted criteria and/or a dedicated review table. At minimum persist:

- `review_status`
- `reviewed_by`
- `reviewed_at`
- `review_notes`
- corrected structured values
- original extracted values

If review edits can materially rewrite criteria, prefer an append-only audit shape over destructive overwrite.

**Why**

- Review is part of the product, not just an API action.
- Clinical data workflows need traceability.
- Corrected outputs become high-value evaluation data for later pipeline tuning.

### 4. Make internal criterion JSON the canonical MVP representation

FHIR export is useful, but FHIR R4 is not a clean primary storage contract for detailed eligibility logic.

**Recommendation**

- Treat internal extracted criterion JSON and relational tables as the canonical representation.
- Keep FHIR `ResearchStudy` output as a derived/export view.
- Adjust the spec language so FHIR alignment is an interoperability goal, not the primary modeling constraint.

**Why**

- Avoids forcing complex oncology logic into an awkward standard too early.
- Keeps the MVP storage model practical.
- Preserves flexibility as the extraction schema evolves.

### 5. Broaden or explicitly make the criterion schema extensible for oncology

The current categories are a good start, but oncology trials often depend on factors not yet captured.

**Add support for categories such as**

- disease stage or resectability
- histology or subtype
- molecular alteration status
- prior lines of therapy or refractory status
- CNS metastases status
- concomitant medications

**Recommendation**

- Either expand the category list now, or
- make category extension explicit in the spec through a controlled vocabulary plus flexible structured payload fields.

**Why**

- These criteria are common and clinically important in oncology.
- Retrofitting them later will be more expensive if the schema is too rigid now.

### 6. Define ingestion idempotency and update behavior

The spec should be explicit about what happens when the same NCT ID is ingested multiple times or when ClinicalTrials.gov updates a study.

**Recommendation**

- Define upsert semantics keyed by `nct_id`.
- Compare source content using `last_updated` and/or a normalized content hash.
- Trigger re-extraction only when source content relevant to extraction changed.
- Clarify whether historical raw payloads are retained or only the latest payload is kept.

**Why**

- Prevents duplicate data and unnecessary extraction work.
- Makes ingestion predictable.
- Avoids ambiguity around source updates.

### 7. Add indexing and search strategy to the spec

This service will need fast retrieval early, especially for trial lookup, review queues, and criterion filtering.

**Recommendation**

Document expected indexes, at minimum on:

- `trials.nct_id`
- `trials.status`
- `trials.phase`
- `trials.conditions`
- `trial_sites.trial_id`
- `extracted_criteria.trial_id`
- `extracted_criteria.review_required`
- `extracted_criteria.category`

Also consider GIN indexes for:

- arrays such as `conditions`
- JSONB fields such as `coded_concepts` or raw source fragments

**Why**

- Search performance becomes visible quickly in this workflow.
- Indexing choices materially affect API design and query shape.

### 8. Preserve non-parseable but clinically important criteria

Some eligibility text will be too complex for rule-based extraction but still too important to drop.

**Recommendation**

Add a fallback representation such as:

- `unparsed_criterion_fragments`
- `review_only` criteria
- a parse-status field on extracted rows with raw text preserved

The core requirement is that no clinically relevant text disappears because parsing failed.

**Why**

- Prevents silent data loss.
- Gives reviewers a safe fallback path.
- Supports gradual parser improvement without sacrificing coverage.

## Suggested MVP Framing

If the spec is revised, the MVP should emphasize:

- canonical internal storage first
- auditable extraction runs
- explicit human review persistence
- deterministic ingestion and re-ingestion behavior
- extensible oncology criterion modeling

FHIR export can remain in scope, but as a derived compatibility layer rather than the core storage contract.

## External Source Provenance Notes

The implementation and validation work on top of this spec has used official external sources only where the code needed source-text or terminology verification beyond the repository fixtures.

- ClinicalTrials.gov study records were used to derive and validate real eligibility-text fixtures:
  - `NCT03872596` for a CYP3A4 inhibitor/inducer washout restriction
  - `NCT07084584` for a CYP3A4 exception-clause restriction
- ClinicalTrials.gov data-API documentation and study-data structure pages were used when validating ingestion and search semantics for the V2 API.
- NCI Drug Dictionary pages were used to validate seeded NCIt drug identifiers and synonym coverage, including carboplatin, docetaxel, and capecitabine.

A detailed source ledger with exact URLs, dates, and implementation notes is tracked locally in ignored context so the public repository keeps the outline-level documentation while still preserving provenance during development.
