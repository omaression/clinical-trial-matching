import logging
import re
from dataclasses import dataclass

import httpx
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.extraction.coding.entity_coder import EntityCoder
from app.extraction.pipeline import ExtractionPipeline
from app.extraction.types import Entity
from app.fhir.mapper import FHIRMapper
from app.ingestion.ctgov_client import CTGovClient
from app.ingestion.hasher import content_hash
from app.models.database import (
    ExtractedCriterion,
    FHIRResearchStudy,
    PipelineRun,
    Trial,
    TrialSite,
)
from app.scripts.seed import sync_coding_lookups
from app.time_utils import parse_clinicaltrials_datetime, utc_now

logger = logging.getLogger(__name__)

_CODABLE_ENTITY_LABELS_BY_CATEGORY = {
    "diagnosis": {"DISEASE"},
    "disease_stage": {"DISEASE"},
    "histology": {"DISEASE"},
    "cns_metastases": {"DISEASE"},
    "prior_therapy": {"DRUG"},
    "line_of_therapy": {"DRUG"},
    "concomitant_medication": {"DRUG"},
    "molecular_alteration": {"BIOMARKER"},
    "biomarker": {"BIOMARKER"},
    "lab_value": {"LAB_TEST"},
    "performance_status": {"PERF_SCALE"},
    "procedural_requirement": {"PROCEDURE"},
}
_GENERIC_TREATMENT_CLASS_TERMS = {
    "chemotherapy",
    "platinum based chemotherapy",
    "systemic therapy",
    "targeted therapy",
    "immunotherapy",
    "antiretroviral therapy",
    "steroid therapy",
    "immunosuppressive therapy",
    "hormonal therapy",
    "endocrine therapy",
}
_REVIEW_NEUTRAL_TREATMENT_CLASS_TERMS = {
    "pd-1 therapy",
    "pd-1/pd-l1 therapy",
    "pd-1/pd-l1 inhibitor therapy",
    "kras-targeted therapy",
}
_GENERIC_DIAGNOSIS_TERMS = {
    "active infection",
    "inflammatory bowel disease",
    "cardiovascular disorder",
    "cerebrovascular disease",
    "pulmonary illness",
    "pulmonary illnesses",
    "carcinomatous meningitis",
}
_MATCH_TYPE_PRIORITY = {
    "exact": 0,
    "synonym": 1,
    "fuzzy": 2,
}


@dataclass
class IngestionResult:
    trial: Trial
    criteria_count: int = 0
    review_count: int = 0
    skipped: bool = False
    diff_summary: dict | None = None


@dataclass
class SearchIngestTrialResult:
    nct_id: str | None
    trial: Trial | None = None
    criteria_count: int = 0
    skipped: bool = False
    error_message: str | None = None


@dataclass
class SearchIngestBatchResult:
    results: list[SearchIngestTrialResult]
    returned_count: int
    total_count: int | None = None
    next_page_token: str | None = None


class IngestionService:
    def __init__(self, db: Session, pipeline: ExtractionPipeline | None = None):
        self._db = db
        self._client = CTGovClient()
        self._pipeline = pipeline or ExtractionPipeline()
        self._coder = EntityCoder(db)
        self._fhir_mapper = FHIRMapper()

    def _ensure_coding_catalog(self) -> None:
        inserted, updated, total = sync_coding_lookups(self._db)
        self._db.flush()
        if inserted or updated:
            logger.info(
                "synced coding lookup catalog for ingestion service",
                extra={
                    "inserted": inserted,
                    "updated": updated,
                    "total": total,
                },
            )

    def ingest(self, nct_id: str) -> IngestionResult:
        self._ensure_coding_catalog()
        raw_json = self._client.fetch_study(nct_id)
        eligibility_text = self._extract_eligibility_text(raw_json)
        new_hash = content_hash(self._content_hash_material(raw_json))

        # Check for existing trial
        existing = self._db.query(Trial).filter_by(nct_id=nct_id).first()
        if existing and existing.content_hash == new_hash:
            return IngestionResult(trial=existing, skipped=True)

        # Create or update trial
        if existing:
            trial = existing
            self._apply_trial_snapshot(trial, raw_json=raw_json, hash_val=new_hash)
            trial.updated_at = utc_now()
        else:
            trial = self._create_trial(nct_id, raw_json, new_hash)
            self._db.add(trial)

        self._db.flush()
        self._persist_sites(trial, raw_json)

        # Create pipeline run
        run = PipelineRun(
            trial_id=trial.id,
            pipeline_version=settings.pipeline_version,
            input_hash=content_hash(eligibility_text),
            input_snapshot=raw_json,
            status="running",
        )
        self._db.add(run)
        self._db.flush()

        try:
            result = self._pipeline.extract(eligibility_text)
            criteria_count, review_count = self._persist_criteria(trial, run, result)
            self._persist_fhir(trial, run, result)

            run.status = "completed"
            run.finished_at = utc_now()
            run.criteria_extracted_count = criteria_count
            run.review_required_count = review_count
            trial.extraction_status = "completed"

            self._db.commit()

            return IngestionResult(
                trial=trial,
                criteria_count=criteria_count,
                review_count=review_count,
            )

        except Exception as e:
            run.status = "failed"
            run.finished_at = utc_now()
            run.error_message = str(e)
            trial.extraction_status = "failed"
            self._db.commit()
            raise

    def re_extract(self, trial: Trial) -> IngestionResult:
        """Re-run the extraction pipeline on a trial's stored raw_json without re-fetching."""
        self._ensure_coding_catalog()
        eligibility_text = self._extract_eligibility_text(trial.raw_json)

        previous_run = self._latest_completed_run(trial.id)
        old_criteria = []
        if previous_run:
            old_criteria = (
                self._db.query(ExtractedCriterion)
                .filter(ExtractedCriterion.pipeline_run_id == previous_run.id)
                .all()
            )
        old_texts = {c.original_text for c in old_criteria}
        old_count = len(old_criteria)

        run = PipelineRun(
            trial_id=trial.id,
            pipeline_version=settings.pipeline_version,
            input_hash=content_hash(eligibility_text),
            input_snapshot=trial.raw_json,
            status="running",
        )
        self._db.add(run)
        self._db.flush()

        try:
            result = self._pipeline.extract(eligibility_text)
            criteria_count, review_count = self._persist_criteria(trial, run, result)
            self._persist_fhir(trial, run, result)

            # Compute diff
            new_texts = {c.original_text for c in result.criteria}
            diff_summary = {
                "added": len(new_texts - old_texts),
                "removed": len(old_texts - new_texts),
                "unchanged": len(new_texts & old_texts),
                "previous_count": old_count,
                "new_count": criteria_count,
            }

            run.status = "completed"
            run.finished_at = utc_now()
            run.criteria_extracted_count = criteria_count
            run.review_required_count = review_count
            run.diff_summary = diff_summary
            trial.extraction_status = "completed"

            self._db.commit()

            return IngestionResult(
                trial=trial,
                criteria_count=criteria_count,
                review_count=review_count,
                diff_summary=diff_summary,
            )
        except Exception as e:
            run.status = "failed"
            run.finished_at = utc_now()
            run.error_message = str(e)
            trial.extraction_status = "failed"
            self._db.commit()
            raise

    def search_and_ingest(
        self,
        condition: str | None = None,
        status: str | None = None,
        phase: str | None = None,
        limit: int = 25,
        page_token: str | None = None,
    ) -> SearchIngestBatchResult:
        """Search ClinicalTrials.gov and ingest matching studies."""
        search_result = self._client.search_studies(
            condition=condition, status=status, phase=phase, limit=limit, page_token=page_token,
        )
        if isinstance(search_result, list):
            studies = search_result
            total_count = None
            next_page_token = None
        else:
            studies = search_result.studies
            total_count = search_result.total_count
            next_page_token = search_result.next_page_token

        results: list[SearchIngestTrialResult] = []
        for study in studies:
            nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
            if not nct_id:
                results.append(
                    SearchIngestTrialResult(
                        nct_id=None,
                        error_message="Search result missing NCT ID",
                    )
                )
                continue

            try:
                results.append(self._ingest_search_result(nct_id))
            except Exception as exc:
                logger.exception("search-ingest failed for %s", nct_id)
                results.append(
                    SearchIngestTrialResult(
                        nct_id=nct_id,
                        error_message=self._public_search_error_message(exc),
                    )
                )
        return SearchIngestBatchResult(
            results=results,
            returned_count=len(studies),
            total_count=total_count,
            next_page_token=next_page_token,
        )

    def _ingest_search_result(self, nct_id: str) -> SearchIngestTrialResult:
        bind = self._db.get_bind()
        session_factory = sessionmaker(bind=bind, expire_on_commit=False)
        with session_factory() as session:
            service = IngestionService(session, pipeline=self._pipeline)
            result = service.ingest(nct_id)
            return SearchIngestTrialResult(
                nct_id=nct_id,
                trial=result.trial,
                criteria_count=result.criteria_count,
                skipped=result.skipped,
            )

    def _public_search_error_message(self, exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPError):
            return "ClinicalTrials.gov request failed during trial ingestion"
        if isinstance(exc, SQLAlchemyError):
            return "Trial ingestion persistence failed"
        return "Trial ingestion failed"

    def _content_hash_material(self, raw_json: dict) -> dict:
        protocol = raw_json.get("protocolSection", {})
        identification = protocol.get("identificationModule", {})
        status_module = protocol.get("statusModule", {})
        eligibility = protocol.get("eligibilityModule", {})
        design = protocol.get("designModule", {})
        conditions_module = protocol.get("conditionsModule", {})
        sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
        contacts = protocol.get("contactsLocationsModule", {})

        return {
            "brief_title": identification.get("briefTitle"),
            "official_title": identification.get("officialTitle"),
            "status": status_module.get("overallStatus"),
            "start_date": status_module.get("startDateStruct", {}).get("date"),
            "completion_date": (
                status_module.get("completionDateStruct", {}).get("date")
                or status_module.get("primaryCompletionDateStruct", {}).get("date")
            ),
            "last_updated": status_module.get("lastUpdatePostDateStruct", {}).get("date"),
            "phase": design.get("phases", []),
            "conditions": conditions_module.get("conditions", []),
            "interventions": protocol.get("armsInterventionsModule", {}).get("interventions"),
            "eligibility_text": eligibility.get("eligibilityCriteria", ""),
            "minimum_age": eligibility.get("minimumAge"),
            "maximum_age": eligibility.get("maximumAge"),
            "sex": eligibility.get("sex"),
            "healthy_volunteers": eligibility.get("healthyVolunteers"),
            "structured_eligibility": {
                key: value for key, value in eligibility.items()
                if key not in ("eligibilityCriteria", "minimumAge", "maximumAge", "sex", "healthyVolunteers")
            },
            "sponsor": sponsor_module.get("leadSponsor", {}).get("name"),
            "locations": contacts.get("locations", []),
        }

    def _persist_fhir(self, trial: Trial, run: PipelineRun, result) -> None:
        """Generate and store FHIR ResearchStudy resource."""
        criteria = self._db.query(ExtractedCriterion).filter(
            ExtractedCriterion.trial_id == trial.id,
            ExtractedCriterion.pipeline_run_id == run.id,
        ).all()
        resource = self._fhir_mapper.to_research_study(trial, criteria)

        latest_version = (
            self._db.query(func.max(FHIRResearchStudy.version))
            .filter(FHIRResearchStudy.trial_id == trial.id)
            .scalar()
        ) or 0
        fhir_study = FHIRResearchStudy(
            trial_id=trial.id,
            resource=resource,
            version=latest_version + 1,
            pipeline_run_id=run.id,
        )
        self._db.add(fhir_study)

    def _persist_sites(self, trial: Trial, raw_json: dict) -> None:
        """Parse and persist trial sites from ClinicalTrials.gov response."""
        # Clear existing sites for re-ingestion
        self._db.query(TrialSite).filter(TrialSite.trial_id == trial.id).delete()

        protocol = raw_json.get("protocolSection", {})
        contacts = protocol.get("contactsLocationsModule", {})
        locations = contacts.get("locations", [])

        for loc in locations:
            site = TrialSite(
                trial_id=trial.id,
                facility=loc.get("facility"),
                city=loc.get("city"),
                state=loc.get("state"),
                country=loc.get("country"),
                zip=loc.get("zip"),
                latitude=loc.get("geoPoint", {}).get("lat") if loc.get("geoPoint") else None,
                longitude=loc.get("geoPoint", {}).get("lon") if loc.get("geoPoint") else None,
                status=loc.get("status"),
            )
            self._db.add(site)

    def _persist_criteria(self, trial: Trial, run: PipelineRun, result) -> tuple[int, int]:
        """Enrich extracted criteria with entity coding and persist to DB."""
        persisted_count = 0
        review_count = 0
        for criterion in result.criteria:
            coded_concepts = list(criterion.coded_concepts)
            review_required = criterion.review_required
            review_reason = criterion.review_reason
            confidence = criterion.confidence
            confidence_factors = dict(criterion.confidence_factors or {})
            grounding_matches: list[str] = []
            coding_review_reasons = set()
            therapy_grounding: list[dict[str, object]] = []

            for entity in criterion.entities:
                if not self._should_code_entity(criterion, entity):
                    continue
                coding_result = self._coder.code_entity(
                    entity,
                    context_variants=self._coding_context_variants(criterion, entity),
                    allow_fuzzy=self._should_allow_fuzzy_coding(criterion.category, entity),
                )
                therapy_grounding_status = self._therapy_grounding_status(
                    criterion.category,
                    entity,
                    coding_result,
                )
                if therapy_grounding_status:
                    therapy_grounding.append(therapy_grounding_status)
                coded_concepts.extend(coding_result.concepts)
                if coding_result.concepts:
                    grounding_matches.extend(
                        concept.match_type for concept in coding_result.concepts if concept.match_type
                    )
                    confidence = self._merge_grounding_confidence(confidence, coding_result)
                if self._should_ignore_coding_review(criterion, entity, coding_result):
                    continue
                if coding_result.review_required:
                    if coding_result.review_reason:
                        coding_review_reasons.add(coding_result.review_reason)
                    confidence = min(confidence, coding_result.confidence)

            coded_concepts = self._deduplicate_coded_concepts(coded_concepts)
            if grounding_matches:
                confidence_factors["ontology_grounding"] = grounding_matches
            confidence_factors["coded_concept_count"] = len(coded_concepts)
            if therapy_grounding:
                confidence_factors["therapy_class_grounding"] = therapy_grounding

            if coding_review_reasons and not review_required:
                review_required = True
                review_reason = self._aggregate_coding_review_reason(coding_review_reasons)
            if review_required and review_reason in {"uncoded_entity", "mixed_coding_review"}:
                confidence_factors["ungrounded_key_slots"] = self._ungrounded_key_slots(
                    criterion,
                    coded_concepts,
                )

            db_criterion = ExtractedCriterion(
                trial_id=trial.id,
                type=criterion.type,
                category=criterion.category,
                primary_semantic_category=criterion.primary_semantic_category or criterion.category,
                secondary_semantic_tags=list(criterion.secondary_semantic_tags),
                parse_status=criterion.parse_status,
                original_text=criterion.original_text,
                source_sentence=criterion.source_sentence,
                source_clause_text=criterion.source_clause_text or criterion.original_text,
                operator=criterion.operator,
                value_low=criterion.value_low,
                value_high=criterion.value_high,
                value_text=criterion.value_text,
                unit=criterion.unit,
                raw_expression=criterion.raw_expression,
                negated=criterion.negated,
                timeframe_operator=criterion.timeframe_operator,
                timeframe_value=criterion.timeframe_value,
                timeframe_unit=criterion.timeframe_unit,
                specimen_type=criterion.specimen_type,
                testing_modality=criterion.testing_modality,
                disease_subtype=criterion.disease_subtype,
                histology_text=criterion.histology_text,
                assay_context=criterion.assay_context,
                exception_logic=criterion.exception_logic,
                exception_entities=list(criterion.exception_entities),
                allowance_text=criterion.allowance_text,
                logic_group_id=criterion.logic_group_id,
                logic_operator=criterion.logic_operator,
                coded_concepts=[c.model_dump() for c in coded_concepts],
                confidence=confidence,
                confidence_factors=confidence_factors,
                review_required=review_required,
                review_reason=review_reason,
                review_status="pending" if review_required else None,
                original_extracted=self._criterion_provenance_snapshot(criterion),
                pipeline_version=settings.pipeline_version,
                pipeline_run_id=run.id,
            )
            self._db.add(db_criterion)
            persisted_count += 1
            if review_required:
                review_count += 1

        return persisted_count, review_count

    def _aggregate_coding_review_reason(self, reasons: set[str]) -> str | None:
        normalized = {reason for reason in reasons if reason}
        if not normalized:
            return None
        if len(normalized) == 1:
            return next(iter(normalized))
        return "mixed_coding_review"

    def _deduplicate_coded_concepts(self, concepts):
        unique: dict[tuple[str, str], object] = {}
        for concept in concepts:
            key = (concept.system, concept.code)
            existing = unique.get(key)
            if existing is None or self._coded_concept_sort_key(concept) < self._coded_concept_sort_key(existing):
                unique[key] = concept
        return list(unique.values())

    def _coded_concept_sort_key(self, concept) -> tuple[int, str]:
        return (
            _MATCH_TYPE_PRIORITY.get(concept.match_type or "", len(_MATCH_TYPE_PRIORITY)),
            concept.display.casefold(),
        )

    def _should_code_entity(self, criterion, entity: Entity) -> bool:
        category = criterion.category
        allowed_labels = _CODABLE_ENTITY_LABELS_BY_CATEGORY.get(category)
        if allowed_labels is None:
            return False
        if entity.label not in allowed_labels:
            return False
        if (
            category == "concomitant_medication"
            and entity.label == "DRUG"
            and any(
                _clean_semantic_text(entity.expanded_text or entity.text)
                == _clean_semantic_text(exception_entity)
                for exception_entity in (criterion.exception_entities or [])
            )
        ):
            return False
        if (
            category in {"prior_therapy", "concomitant_medication"}
            and entity.label == "DRUG"
            and self._is_generic_treatment_entity(entity)
        ):
            return False
        return True

    def _is_generic_treatment_entity(self, entity: Entity) -> bool:
        return self._normalized_entity_text(entity) in _GENERIC_TREATMENT_CLASS_TERMS

    def _is_generic_diagnosis_entity(self, entity: Entity) -> bool:
        return self._normalized_entity_text(entity) in _GENERIC_DIAGNOSIS_TERMS

    def _is_review_neutral_treatment_entity(self, entity: Entity) -> bool:
        therapy_class = self._therapy_class_term(entity)
        return therapy_class in _REVIEW_NEUTRAL_TREATMENT_CLASS_TERMS

    def _normalized_entity_text(self, entity: Entity) -> str:
        source = (entity.expanded_text or entity.text).casefold()
        normalized = re.sub(r"\s+", " ", source).strip()
        return normalized

    def _should_allow_fuzzy_coding(self, category: str, entity: Entity) -> bool:
        if (
            category in {"prior_therapy", "concomitant_medication"}
            and entity.label == "DRUG"
            and self._therapy_class_term(entity) is not None
        ):
            return False
        if (
            category in {"diagnosis", "cns_metastases"}
            and entity.label == "DISEASE"
            and self._is_generic_diagnosis_entity(entity)
        ):
            return False
        return True

    def _criterion_provenance_snapshot(self, criterion) -> dict | None:
        snapshot: dict[str, object] = {}
        source_sentence = getattr(criterion, "source_sentence", None)
        source_clause_text = getattr(criterion, "source_clause_text", None)
        if source_sentence:
            snapshot["source_sentence"] = source_sentence
        if source_clause_text:
            snapshot["source_clause_text"] = source_clause_text
        if getattr(criterion, "specimen_type", None):
            snapshot["specimen_type"] = criterion.specimen_type
        if getattr(criterion, "testing_modality", None):
            snapshot["testing_modality"] = criterion.testing_modality
        if getattr(criterion, "assay_context", None):
            snapshot["assay_context"] = criterion.assay_context
        if getattr(criterion, "exception_logic", None):
            snapshot["exception_logic"] = criterion.exception_logic
        if getattr(criterion, "exception_entities", None):
            snapshot["exception_entities"] = list(criterion.exception_entities)
        if getattr(criterion, "allowance_text", None):
            snapshot["allowance_text"] = criterion.allowance_text
        return snapshot or None

    def _merge_grounding_confidence(self, confidence: float, coding_result) -> float:
        match_types = {concept.match_type for concept in coding_result.concepts}
        if "exact" in match_types:
            return max(confidence, 0.90)
        if "synonym" in match_types:
            return max(confidence, 0.82)
        if "fuzzy" in match_types:
            return min(confidence, 0.60)
        return confidence

    def _should_ignore_coding_review(self, criterion, entity: Entity, coding_result) -> bool:
        category = criterion.category
        if (
            category in {"diagnosis", "cns_metastases"}
            and entity.label == "DISEASE"
            and self._is_generic_diagnosis_entity(entity)
            and not coding_result.concepts
            and coding_result.review_reason == "uncoded_entity"
        ):
            return True
        if (
            category in {"prior_therapy", "concomitant_medication"}
            and entity.label == "DRUG"
            and self._is_review_neutral_treatment_entity(entity)
            and not coding_result.concepts
            and coding_result.review_reason == "uncoded_entity"
        ):
            return True
        if (
            category == "concomitant_medication"
            and getattr(criterion, "exception_logic", None)
            and entity.label == "DRUG"
            and not coding_result.concepts
            and coding_result.review_reason == "uncoded_entity"
        ):
            return True
        return False

    def _coding_context_variants(self, criterion, entity: Entity) -> list[str]:
        if entity.label not in {"DISEASE", "DRUG", "BIOMARKER"}:
            return []

        variants: list[str] = []
        therapy_class = self._therapy_class_term(entity)
        if therapy_class and therapy_class not in variants:
            variants.append(therapy_class)
        for peer in criterion.entities:
            if peer is entity or peer.label != entity.label:
                continue
            if not self._entities_share_alias_context(criterion.original_text, entity, peer):
                continue
            for value in (peer.expanded_text, peer.text):
                if value and value not in variants:
                    variants.append(value)
        return variants

    def _entities_share_alias_context(self, criterion_text: str, entity: Entity, peer: Entity) -> bool:
        candidate_pairs = []
        for left in (entity.text, entity.expanded_text):
            if not left:
                continue
            for right in (peer.text, peer.expanded_text):
                if not right or left == right:
                    continue
                candidate_pairs.append((left, right))

        for left, right in candidate_pairs:
            if self._has_alias_separator(criterion_text, left, right):
                return True
        return False

    def _therapy_grounding_status(
        self,
        category: str,
        entity: Entity,
        coding_result,
    ) -> dict[str, object] | None:
        if category not in {"prior_therapy", "concomitant_medication"} or entity.label != "DRUG":
            return None
        canonical_term = self._therapy_class_term(entity)
        if canonical_term is None:
            return None
        if coding_result.concepts:
            return {
                "term": canonical_term,
                "status": "grounded",
                "match_types": [concept.match_type for concept in coding_result.concepts if concept.match_type],
            }
        return {
            "term": canonical_term,
            "status": "recognized_ungrounded",
        }

    def _therapy_class_term(self, entity: Entity) -> str | None:
        normalized = _clean_semantic_text(entity.expanded_text or entity.text)
        has_pd1 = (
            "pd 1" in normalized
            or "programmed cell death protein 1" in normalized
        )
        has_pdl1 = (
            "pd l1" in normalized
            or "pdl1" in normalized
            or "programmed death ligand 1" in normalized
            or "programmed death ligands 1" in normalized
        )
        if has_pd1 and has_pdl1 and "inhibitor" in normalized:
            return "pd-1/pd-l1 inhibitor therapy"
        if has_pd1 and has_pdl1 and ("therapy" in normalized or "antibody" in normalized):
            return "pd-1/pd-l1 therapy"
        if has_pdl1 and ("therapy" in normalized or "inhibitor" in normalized or "antibody" in normalized):
            return "pd-l1 therapy"
        if has_pd1 and ("therapy" in normalized or "inhibitor" in normalized or "antibody" in normalized):
            return "pd-1 therapy"
        if "kras" in normalized and any(token in normalized for token in ("target", "inhibitor")):
            return "kras-targeted therapy"
        return None

    def _ungrounded_key_slots(self, criterion, coded_concepts) -> list[str]:
        if coded_concepts:
            return []
        if criterion.category in {"molecular_alteration", "biomarker"}:
            return ["molecular_concept"]
        if criterion.category in {"prior_therapy", "concomitant_medication"}:
            return ["therapy_or_medication_concept"]
        if criterion.category in {"diagnosis", "cns_metastases"}:
            return ["diagnosis_concept"]
        return []

    def _has_alias_separator(self, criterion_text: str, left: str, right: str) -> bool:
        patterns = (
            rf"{re.escape(left)}\s*/\s*{re.escape(right)}",
            rf"{re.escape(right)}\s*/\s*{re.escape(left)}",
            rf"{re.escape(left)}\s*\(\s*{re.escape(right)}\s*\)",
            rf"{re.escape(right)}\s*\(\s*{re.escape(left)}\s*\)",
        )
        return any(re.search(pattern, criterion_text, re.I) for pattern in patterns)

    def _latest_completed_run(self, trial_id) -> PipelineRun | None:
        return (
            self._db.query(PipelineRun)
            .filter(
                PipelineRun.trial_id == trial_id,
                PipelineRun.status == "completed",
            )
            .order_by(PipelineRun.finished_at.desc().nullslast(), PipelineRun.started_at.desc())
            .first()
        )

    def _extract_eligibility_text(self, raw_json: dict) -> str:
        protocol = raw_json.get("protocolSection", {})
        eligibility = protocol.get("eligibilityModule", {})
        return eligibility.get("eligibilityCriteria", "")

    def _create_trial(self, nct_id: str, raw_json: dict, hash_val: str) -> Trial:
        return Trial(**self._trial_snapshot(nct_id=nct_id, raw_json=raw_json, hash_val=hash_val))

    def _apply_trial_snapshot(self, trial: Trial, raw_json: dict, hash_val: str) -> None:
        snapshot = self._trial_snapshot(nct_id=trial.nct_id, raw_json=raw_json, hash_val=hash_val)
        for field, value in snapshot.items():
            setattr(trial, field, value)

    def _trial_snapshot(self, nct_id: str, raw_json: dict, hash_val: str) -> dict:
        protocol = raw_json.get("protocolSection", {})
        identification = protocol.get("identificationModule", {})
        status_module = protocol.get("statusModule", {})
        eligibility = protocol.get("eligibilityModule", {})
        design = protocol.get("designModule", {})
        conditions_module = protocol.get("conditionsModule", {})
        sponsor_module = protocol.get("sponsorCollaboratorsModule", {})

        return {
            "nct_id": nct_id,
            "raw_json": raw_json,
            "content_hash": hash_val,
            "brief_title": identification.get("briefTitle", ""),
            "official_title": identification.get("officialTitle"),
            "status": status_module.get("overallStatus", "UNKNOWN"),
            "phase": ",".join(design.get("phases", [])),
            "conditions": conditions_module.get("conditions", []),
            "interventions": protocol.get("armsInterventionsModule", {}).get("interventions"),
            "eligibility_text": eligibility.get("eligibilityCriteria", ""),
            "eligible_min_age": eligibility.get("minimumAge"),
            "eligible_max_age": eligibility.get("maximumAge"),
            "eligible_sex": eligibility.get("sex"),
            "accepts_healthy": eligibility.get("healthyVolunteers") == "Yes",
            "structured_eligibility": {
                k: v for k, v in eligibility.items()
                if k not in ("eligibilityCriteria", "minimumAge", "maximumAge", "sex", "healthyVolunteers")
            } or None,
            "sponsor": sponsor_module.get("leadSponsor", {}).get("name"),
            "start_date": parse_clinicaltrials_datetime(status_module.get("startDateStruct", {}).get("date")),
            "completion_date": parse_clinicaltrials_datetime(
                status_module.get("completionDateStruct", {}).get("date")
                or status_module.get("primaryCompletionDateStruct", {}).get("date")
            ),
            "last_updated": parse_clinicaltrials_datetime(
                status_module.get("lastUpdatePostDateStruct", {}).get("date")
            ),
        }


def _clean_semantic_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.casefold()
    normalized = normalized.replace("+", " positive ")
    normalized = normalized.replace("/", " ")
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()
