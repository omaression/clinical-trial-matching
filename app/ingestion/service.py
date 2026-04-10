from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.extraction.coding.entity_coder import EntityCoder
from app.extraction.pipeline import ExtractionPipeline
from app.ingestion.ctgov_client import CTGovClient
from app.ingestion.hasher import content_hash
from app.models.database import (
    ExtractedCriterion,
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


class IngestionService:
    def __init__(self, db: Session):
        self._db = db
        self._client = CTGovClient()
        self._pipeline = ExtractionPipeline()
        self._coder = EntityCoder(db)

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
            # Run extraction
            result = self._pipeline.extract(eligibility_text)

            # Persist criteria with coding
            for criterion in result.criteria:
                # Enrich with entity coding
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

            # Update run and trial status
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
