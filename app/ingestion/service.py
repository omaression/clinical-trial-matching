import logging
from dataclasses import dataclass

import httpx
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.extraction.coding.entity_coder import EntityCoder
from app.extraction.pipeline import ExtractionPipeline
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

    def ingest(self, nct_id: str) -> IngestionResult:
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
            coding_review_reasons = set()

            for entity in criterion.entities:
                if not self._should_code_entity(criterion.category, entity.label):
                    continue
                coding_result = self._coder.code_entity(entity)
                coded_concepts.extend(coding_result.concepts)
                if coding_result.review_required:
                    if coding_result.review_reason:
                        coding_review_reasons.add(coding_result.review_reason)
                    confidence = min(confidence, coding_result.confidence)

            if coding_review_reasons and not review_required:
                review_required = True
                review_reason = self._aggregate_coding_review_reason(coding_review_reasons)

            db_criterion = ExtractedCriterion(
                trial_id=trial.id,
                type=criterion.type,
                category=criterion.category,
                parse_status=criterion.parse_status,
                original_text=criterion.original_text,
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
                logic_group_id=criterion.logic_group_id,
                logic_operator=criterion.logic_operator,
                coded_concepts=[c.model_dump() for c in coded_concepts],
                confidence=confidence,
                review_required=review_required,
                review_reason=review_reason,
                review_status="pending" if review_required else None,
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

    def _should_code_entity(self, category: str, label: str) -> bool:
        allowed_labels = _CODABLE_ENTITY_LABELS_BY_CATEGORY.get(category)
        if allowed_labels is None:
            return False
        return label in allowed_labels

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
