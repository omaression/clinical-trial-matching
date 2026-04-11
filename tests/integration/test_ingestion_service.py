import copy
import json
import uuid
from pathlib import Path
from unittest.mock import patch

import docker
import pytest

from app.extraction.coding.entity_coder import CodingResult
from app.extraction.types import ClassifiedCriterion, CodedConcept, Entity, PipelineResult
from app.ingestion.hasher import content_hash
from app.ingestion.service import IngestionService
from app.models.database import ExtractedCriterion, FHIRResearchStudy, PipelineRun, Trial

MOCK_DIR = Path(__file__).parent.parent / "fixtures" / "mock_ctgov_responses"


def _docker_available():
    try:
        docker.from_env().ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _docker_available(), reason="Docker not available")


def _unique_mock_response():
    """Load mock response and assign a unique NCT ID to avoid cross-test collisions."""
    data = json.loads((MOCK_DIR / "NCT04567890.json").read_text())
    nct_id = f"NCT{uuid.uuid4().hex[:8].upper()}"
    data["protocolSection"]["identificationModule"]["nctId"] = nct_id
    return nct_id, data


@pytest.fixture
def service(db_session):
    return IngestionService(db_session)


class TestIngestSingleTrial:
    def test_ingests_and_extracts(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        with patch.object(service._client, "fetch_study", return_value=mock_resp):
            result = service.ingest(nct_id)

        assert result.trial.nct_id == nct_id
        assert result.trial.extraction_status == "completed"
        assert result.criteria_count > 0

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).first()
        assert trial is not None
        run = db_session.query(PipelineRun).filter_by(trial_id=trial.id).first()
        assert run is not None
        assert run.status == "completed"
        assert run.input_snapshot is not None

    def test_ingest_aggregates_mixed_coding_review_reasons_and_counts(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        pipeline_result = PipelineResult(
            criteria=[
                ClassifiedCriterion(
                    original_text="Confirmed breast cancr with HER2-positive disease",
                    type="inclusion",
                    category="diagnosis",
                    parse_status="parsed",
                    confidence=0.85,
                    entities=[
                        Entity(text="breast cancr", label="DISEASE", start=10, end=22),
                        Entity(text="HER2-positive", label="BIOMARKER", start=28, end=41),
                    ],
                )
            ],
            pipeline_version="0.1.0",
        )
        coding_results = [
            CodingResult(
                concepts=[
                    CodedConcept(
                        system="mesh",
                        code="D001943",
                        display="Breast Neoplasms",
                        match_type="fuzzy",
                    )
                ],
                confidence=0.60,
                review_required=True,
                review_reason="fuzzy_match",
            ),
            CodingResult(
                concepts=[],
                confidence=0.40,
                review_required=True,
                review_reason="uncoded_entity",
            ),
        ]

        with (
            patch.object(service._client, "fetch_study", return_value=mock_resp),
            patch.object(service._pipeline, "extract", return_value=pipeline_result),
            patch.object(service._coder, "code_entity", side_effect=coding_results),
        ):
            result = service.ingest(nct_id)

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).first()
        run = (
            db_session.query(PipelineRun)
            .filter_by(trial_id=trial.id)
            .order_by(PipelineRun.started_at.desc())
            .first()
        )
        criterion = db_session.query(ExtractedCriterion).filter_by(trial_id=trial.id).one()

        assert result.criteria_count == 1
        assert result.review_count == 1
        assert run.criteria_extracted_count == 1
        assert run.review_required_count == 1
        assert criterion.review_required is True
        assert criterion.review_reason == "mixed_coding_review"
        assert criterion.confidence == 0.40
        assert criterion.review_status == "pending"
        assert criterion.coded_concepts == [
            {
                "system": "mesh",
                "code": "D001943",
                "display": "Breast Neoplasms",
                "match_type": "fuzzy",
            }
        ]

    def test_ingest_preserves_non_coding_review_reason_while_counting_coding_flags(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        pipeline_result = PipelineResult(
            criteria=[
                ClassifiedCriterion(
                    original_text="No prior treatment with trastuzumab, unless administered more than 6 months ago",
                    type="exclusion",
                    category="prior_therapy",
                    parse_status="partial",
                    confidence=0.30,
                    review_required=True,
                    review_reason="complex_criteria",
                    entities=[Entity(text="trastuzumab", label="DRUG", start=24, end=35)],
                )
            ],
            pipeline_version="0.1.0",
        )
        coding_result = CodingResult(
            concepts=[],
            confidence=0.40,
            review_required=True,
            review_reason="uncoded_entity",
        )

        with (
            patch.object(service._client, "fetch_study", return_value=mock_resp),
            patch.object(service._pipeline, "extract", return_value=pipeline_result),
            patch.object(service._coder, "code_entity", return_value=coding_result),
        ):
            result = service.ingest(nct_id)

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).first()
        run = db_session.query(PipelineRun).filter_by(trial_id=trial.id).one()
        criterion = db_session.query(ExtractedCriterion).filter_by(trial_id=trial.id).one()

        assert result.review_count == 1
        assert run.review_required_count == 1
        assert criterion.review_required is True
        assert criterion.review_reason == "complex_criteria"
        assert criterion.confidence == 0.30


class TestIdempotency:
    def test_reingest_unchanged_skips(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        with patch.object(service._client, "fetch_study", return_value=mock_resp):
            result1 = service.ingest(nct_id)
            result2 = service.ingest(nct_id)

        assert result2.skipped is True
        runs = db_session.query(PipelineRun).filter_by(trial_id=result1.trial.id).count()
        assert runs == 1

    def test_reingest_changed_reextracts(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        with patch.object(service._client, "fetch_study", return_value=mock_resp):
            result1 = service.ingest(nct_id)

        changed = copy.deepcopy(mock_resp)
        changed["protocolSection"]["eligibilityModule"]["eligibilityCriteria"] = "Age >= 21 years"
        with patch.object(service._client, "fetch_study", return_value=changed):
            result2 = service.ingest(nct_id)

        assert result2.skipped is False
        runs = db_session.query(PipelineRun).filter_by(trial_id=result1.trial.id).count()
        assert runs == 2

    def test_reingest_changed_source_fields_reextracts_and_preserves_run_history(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        with patch.object(service._client, "fetch_study", return_value=mock_resp):
            result1 = service.ingest(nct_id)

        changed = copy.deepcopy(mock_resp)
        changed["protocolSection"]["identificationModule"]["briefTitle"] = "Updated Study Title"
        changed["protocolSection"]["statusModule"]["overallStatus"] = "COMPLETED"
        changed["protocolSection"]["eligibilityModule"]["minimumAge"] = "21 Years"

        with patch.object(service._client, "fetch_study", return_value=changed):
            result2 = service.ingest(nct_id)

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).first()
        runs = db_session.query(PipelineRun).filter_by(trial_id=trial.id).count()
        latest_run = (
            db_session.query(PipelineRun)
            .filter_by(trial_id=trial.id)
            .order_by(PipelineRun.started_at.desc())
            .first()
        )
        total_criteria = db_session.query(ExtractedCriterion).filter_by(trial_id=trial.id).count()
        latest_criteria_count = db_session.query(ExtractedCriterion).filter_by(
            trial_id=trial.id,
            pipeline_run_id=latest_run.id,
        ).count()
        fhir_versions = [
            row.version
            for row in db_session.query(FHIRResearchStudy)
            .filter_by(trial_id=trial.id)
            .order_by(FHIRResearchStudy.version.asc())
            .all()
        ]

        assert result2.skipped is False
        assert runs == 2
        assert trial.brief_title == "Updated Study Title"
        assert trial.status == "COMPLETED"
        assert trial.eligible_min_age == "21 Years"
        assert total_criteria == result1.criteria_count + result2.criteria_count
        assert latest_criteria_count == result2.criteria_count
        assert fhir_versions == [1, 2]

    def test_reextract_appends_history_and_diffs_against_previous_completed_run(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        with patch.object(service._client, "fetch_study", return_value=mock_resp):
            first_result = service.ingest(nct_id)

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).first()
        second_result = service.re_extract(trial)

        runs = (
            db_session.query(PipelineRun)
            .filter_by(trial_id=trial.id, status="completed")
            .order_by(PipelineRun.started_at.asc())
            .all()
        )
        criteria_by_run = {
            run.id: db_session.query(ExtractedCriterion).filter_by(pipeline_run_id=run.id).count()
            for run in runs
        }
        fhir_versions = [
            row.version
            for row in db_session.query(FHIRResearchStudy)
            .filter_by(trial_id=trial.id)
            .order_by(FHIRResearchStudy.version.asc())
            .all()
        ]

        assert len(runs) == 2
        assert second_result.criteria_count == first_result.criteria_count
        assert criteria_by_run[runs[0].id] == first_result.criteria_count
        assert criteria_by_run[runs[1].id] == second_result.criteria_count
        assert second_result.diff_summary == {
            "added": 0,
            "removed": 0,
            "unchanged": first_result.criteria_count,
            "previous_count": first_result.criteria_count,
            "new_count": second_result.criteria_count,
        }
        assert fhir_versions == [1, 2]

    def test_reextract_failure_preserves_existing_criteria(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        with patch.object(service._client, "fetch_study", return_value=mock_resp):
            result = service.ingest(nct_id)

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).first()
        original_count = db_session.query(ExtractedCriterion).filter_by(trial_id=trial.id).count()

        with patch.object(service._pipeline, "extract", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                service.re_extract(trial)

        criteria_count = db_session.query(ExtractedCriterion).filter_by(trial_id=trial.id).count()
        fhir_count = db_session.query(FHIRResearchStudy).filter_by(trial_id=trial.id).count()
        latest_run = (
            db_session.query(PipelineRun)
            .filter_by(trial_id=trial.id)
            .order_by(PipelineRun.started_at.desc())
            .first()
        )

        assert criteria_count == original_count
        assert original_count == result.criteria_count
        assert fhir_count == 1
        assert latest_run.status == "failed"


class TestContentHash:
    def test_hash_deterministic(self):
        h1 = content_hash("some eligibility text")
        h2 = content_hash("some eligibility text")
        assert h1 == h2

    def test_hash_differs_on_change(self):
        h1 = content_hash("Age >= 18")
        h2 = content_hash("Age >= 21")
        assert h1 != h2
