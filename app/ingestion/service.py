from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

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


@dataclass
class IngestionResult:
    trial: Trial
    criteria_count: int = 0
    review_count: int = 0
    skipped: bool = False
    diff_summary: dict | None = None


class IngestionService:
    def __init__(self, db: Session):
        self._db = db
        self._client = CTGovClient()
        self._pipeline = ExtractionPipeline()
        self._coder = EntityCoder(db)
        self._fhir_mapper = FHIRMapper()

    def ingest(self, nct_id: str) -> IngestionResult:
        raw_json = self._client.fetch_study(nct_id)
        eligibility_text = self._extract_eligibility_text(raw_json)
        new_hash = content_hash(eligibility_text)

        # Check for existing trial
        existing = self._db.query(Trial).filter_by(nct_id=nct_id).first()
        if existing and existing.content_hash == new_hash:
            return IngestionResult(trial=existing, skipped=True)

        # Create or update trial
        if existing:
            trial = existing
            trial.raw_json = raw_json
            trial.content_hash = new_hash
            trial.updated_at = datetime.utcnow()
        else:
            trial = self._create_trial(nct_id, raw_json, new_hash)
            self._db.add(trial)

        self._db.flush()

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
            self._persist_criteria(trial, run, result)
            self._persist_fhir(trial, run, result)
            self._persist_sites(trial, raw_json)

            run.status = "completed"
            run.finished_at = datetime.utcnow()
            run.criteria_extracted_count = result.criteria_count
            run.review_required_count = result.review_required_count
            trial.extraction_status = "completed"

            self._db.commit()

            return IngestionResult(
                trial=trial,
                criteria_count=result.criteria_count,
                review_count=result.review_required_count,
            )

        except Exception as e:
            run.status = "failed"
            run.finished_at = datetime.utcnow()
            run.error_message = str(e)
            trial.extraction_status = "failed"
            self._db.commit()
            raise

    def re_extract(self, trial: Trial) -> IngestionResult:
        """Re-run the extraction pipeline on a trial's stored raw_json without re-fetching."""
        eligibility_text = self._extract_eligibility_text(trial.raw_json)

        # Snapshot old criteria categories for diff
        old_criteria = self._db.query(ExtractedCriterion).filter(
            ExtractedCriterion.trial_id == trial.id
        ).all()
        old_texts = {c.original_text for c in old_criteria}
        old_count = len(old_criteria)

        # Delete old criteria
        self._db.query(ExtractedCriterion).filter(
            ExtractedCriterion.trial_id == trial.id
        ).delete()

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
            self._persist_criteria(trial, run, result)
            self._persist_fhir(trial, run, result)

            # Compute diff
            new_texts = {c.original_text for c in result.criteria}
            diff_summary = {
                "added": len(new_texts - old_texts),
                "removed": len(old_texts - new_texts),
                "unchanged": len(new_texts & old_texts),
                "previous_count": old_count,
                "new_count": result.criteria_count,
            }

            run.status = "completed"
            run.finished_at = datetime.utcnow()
            run.criteria_extracted_count = result.criteria_count
            run.review_required_count = result.review_required_count
            run.diff_summary = diff_summary
            trial.extraction_status = "completed"

            self._db.commit()

            return IngestionResult(
                trial=trial,
                criteria_count=result.criteria_count,
                review_count=result.review_required_count,
                diff_summary=diff_summary,
            )
        except Exception as e:
            run.status = "failed"
            run.finished_at = datetime.utcnow()
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
    ) -> list[IngestionResult]:
        """Search ClinicalTrials.gov and ingest matching studies."""
        studies = self._client.search_studies(
            condition=condition, status=status, phase=phase, limit=limit,
        )
        results = []
        for study in studies:
            nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
            if nct_id:
                result = self.ingest(nct_id)
                results.append(result)
        return results

    def _persist_fhir(self, trial: Trial, run: PipelineRun, result) -> None:
        """Generate and store FHIR ResearchStudy resource."""
        criteria = self._db.query(ExtractedCriterion).filter(
            ExtractedCriterion.trial_id == trial.id,
            ExtractedCriterion.pipeline_run_id == run.id,
        ).all()
        resource = self._fhir_mapper.to_research_study(trial, criteria)

        # Check for existing FHIR resource
        existing = self._db.query(FHIRResearchStudy).filter_by(trial_id=trial.id).first()
        if existing:
            existing.resource = resource
            existing.version = existing.version + 1
            existing.pipeline_run_id = run.id
            existing.updated_at = datetime.utcnow()
        else:
            fhir_study = FHIRResearchStudy(
                trial_id=trial.id,
                resource=resource,
                version=1,
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

    def _persist_criteria(self, trial: Trial, run: PipelineRun, result) -> None:
        """Enrich extracted criteria with entity coding and persist to DB."""
        for criterion in result.criteria:
            coded_concepts = list(criterion.coded_concepts)
            review_required = criterion.review_required
            review_reason = criterion.review_reason
            confidence = criterion.confidence

            for entity in criterion.entities:
                coding_result = self._coder.code_entity(entity)
                coded_concepts.extend(coding_result.concepts)
                if coding_result.review_required and not review_required:
                    review_required = True
                    review_reason = coding_result.review_reason
                    confidence = min(confidence, coding_result.confidence)

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

    def _extract_eligibility_text(self, raw_json: dict) -> str:
        protocol = raw_json.get("protocolSection", {})
        eligibility = protocol.get("eligibilityModule", {})
        return eligibility.get("eligibilityCriteria", "")

    def _create_trial(self, nct_id: str, raw_json: dict, hash_val: str) -> Trial:
        protocol = raw_json.get("protocolSection", {})
        identification = protocol.get("identificationModule", {})
        status_module = protocol.get("statusModule", {})
        eligibility = protocol.get("eligibilityModule", {})
        design = protocol.get("designModule", {})
        conditions_module = protocol.get("conditionsModule", {})
        sponsor_module = protocol.get("sponsorCollaboratorsModule", {})

        return Trial(
            nct_id=nct_id,
            raw_json=raw_json,
            content_hash=hash_val,
            brief_title=identification.get("briefTitle", ""),
            official_title=identification.get("officialTitle"),
            status=status_module.get("overallStatus", "UNKNOWN"),
            phase=",".join(design.get("phases", [])),
            conditions=conditions_module.get("conditions", []),
            interventions=protocol.get("armsInterventionsModule", {}).get("interventions"),
            eligibility_text=eligibility.get("eligibilityCriteria", ""),
            eligible_min_age=eligibility.get("minimumAge"),
            eligible_max_age=eligibility.get("maximumAge"),
            eligible_sex=eligibility.get("sex"),
            accepts_healthy=eligibility.get("healthyVolunteers") == "Yes",
            structured_eligibility={
                k: v for k, v in eligibility.items()
                if k not in ("eligibilityCriteria", "minimumAge", "maximumAge", "sex", "healthyVolunteers")
            } or None,
            sponsor=sponsor_module.get("leadSponsor", {}).get("name"),
        )
