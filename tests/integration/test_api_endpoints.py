import json
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import docker
import pytest
from fastapi.testclient import TestClient

from app.ingestion.service import SearchIngestTrialResult
from app.main import app
from app.models.database import ExtractedCriterion, PipelineRun, Trial

MOCK_DIR = Path(__file__).parent.parent / "fixtures" / "mock_ctgov_responses"


def _docker_available():
    try:
        docker.from_env().ping()
        return True
    except Exception:
        return False


# --- Non-DB tests (no Docker needed) ---


class TestRouteRegistration:
    def test_openapi_schema_available(self):
        with TestClient(app) as c:
            response = c.get("/openapi.json")
            assert response.status_code == 200
            schema = response.json()
            paths = schema["paths"]
            assert "/api/v1/health" in paths
            assert "/api/v1/trials/ingest" in paths
            assert "/api/v1/trials" in paths
            assert "/api/v1/trials/{trial_id}" in paths
            assert "/api/v1/trials/nct/{nct_id}" in paths
            assert "/api/v1/trials/{trial_id}/criteria" in paths
            assert "/api/v1/criteria/{criterion_id}" in paths
            assert "/api/v1/trials/{trial_id}/fhir" in paths
            assert "/api/v1/review" in paths
            assert "/api/v1/criteria/{criterion_id}/review" in paths
            assert "/api/v1/pipeline/status" in paths
            assert "/api/v1/pipeline/runs" in paths
            assert "/api/v1/pipeline/runs/{run_id}" in paths
            assert "/api/v1/trials/{trial_id}/re-extract" in paths
            assert "/api/v1/trials/search-ingest" in paths


# --- DB-backed tests (require Docker) ---

pytestmark_docker = pytest.mark.skipif(not _docker_available(), reason="Docker not available")


def _parse_api_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _seed_trial(db_session, nct_id=None, status="RECRUITING", phase="PHASE3", conditions=None):
    """Helper to insert a trial with a pipeline run and criteria."""
    nct_id = nct_id or f"NCT{uuid.uuid4().hex[:8].upper()}"
    conditions = conditions or ["Breast Cancer"]
    trial = Trial(
        nct_id=nct_id,
        raw_json={"protocolSection": {"eligibilityModule": {"eligibilityCriteria": "Age >= 18"}}},
        content_hash="test_hash",
        brief_title=f"Test Trial {nct_id}",
        official_title=f"Official Title for {nct_id}",
        status=status,
        phase=phase,
        conditions=conditions,
        eligibility_text="Age >= 18",
        eligible_min_age="18 Years",
        eligible_max_age="75 Years",
        eligible_sex="ALL",
        sponsor="Test Sponsor",
    )
    db_session.add(trial)
    db_session.flush()

    run = PipelineRun(
        trial_id=trial.id,
        pipeline_version="0.1.0",
        input_hash="test_input_hash",
        input_snapshot=trial.raw_json,
        status="completed",
        criteria_extracted_count=2,
        review_required_count=1,
    )
    db_session.add(run)
    db_session.flush()

    c1 = ExtractedCriterion(
        trial_id=trial.id,
        type="inclusion",
        category="age",
        parse_status="parsed",
        original_text="Age >= 18 years",
        operator="gte",
        value_low=18,
        unit="years",
        negated=False,
        confidence=0.95,
        review_required=False,
        coded_concepts=[],
        pipeline_version="0.1.0",
        pipeline_run_id=run.id,
    )
    c2 = ExtractedCriterion(
        trial_id=trial.id,
        type="exclusion",
        category="cns_metastases",
        parse_status="parsed",
        original_text="No active brain metastases",
        negated=True,
        confidence=0.60,
        review_required=True,
        review_reason="fuzzy_match",
        review_status="pending",
        coded_concepts=[{"system": "mesh", "code": "D001859", "display": "Brain Neoplasms", "match_type": "fuzzy"}],
        pipeline_version="0.1.0",
        pipeline_run_id=run.id,
    )
    db_session.add_all([c1, c2])
    db_session.commit()
    return trial, run, c1, c2


def _add_completed_run(db_session, trial, criteria_payloads):
    run = PipelineRun(
        trial_id=trial.id,
        pipeline_version="0.1.0",
        input_hash=f"rehash-{uuid.uuid4().hex}",
        input_snapshot=trial.raw_json,
        status="completed",
        criteria_extracted_count=len(criteria_payloads),
        review_required_count=sum(1 for payload in criteria_payloads if payload.get("review_required")),
    )
    db_session.add(run)
    db_session.flush()

    created = []
    for payload in criteria_payloads:
        criterion = ExtractedCriterion(
            trial_id=trial.id,
            parse_status="parsed",
            negated=False,
            confidence=0.95,
            review_required=False,
            coded_concepts=[],
            pipeline_version="0.1.0",
            pipeline_run_id=run.id,
            **payload,
        )
        db_session.add(criterion)
        created.append(criterion)

    db_session.commit()
    return run, created


@pytestmark_docker
class TestHealthEndpoint:
    def test_health_with_db(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")
        assert "pipeline_version" in data
        assert "database" in data
        assert data["database"] == "connected"
        assert "spacy_model" in data


@pytestmark_docker
class TestListTrials:
    def test_list_empty(self, client):
        response = client.get("/api/v1/trials")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data

    def test_list_with_data(self, client, db_session):
        _seed_trial(db_session)
        response = client.get("/api/v1/trials")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        item = data["items"][0]
        assert "id" in item
        assert "nct_id" in item
        assert "brief_title" in item
        assert "status" in item
        assert "extraction_status" in item

    def test_list_pagination(self, client, db_session):
        for i in range(3):
            _seed_trial(db_session)
        response = client.get("/api/v1/trials?page=1&per_page=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 2
        assert data["per_page"] == 2

    def test_list_filter_by_status(self, client, db_session):
        _seed_trial(db_session, status="RECRUITING")
        _seed_trial(db_session, status="COMPLETED")
        response = client.get("/api/v1/trials?status=RECRUITING")
        assert response.status_code == 200
        for item in response.json()["items"]:
            assert item["status"] == "RECRUITING"

    def test_list_filter_by_phase(self, client, db_session):
        _seed_trial(db_session, phase="PHASE3")
        response = client.get("/api/v1/trials?phase=PHASE3")
        assert response.status_code == 200
        assert response.json()["total"] >= 1

    def test_list_filter_by_condition(self, client, db_session):
        _seed_trial(db_session, conditions=["Melanoma"])
        response = client.get("/api/v1/trials?condition=Melanoma")
        assert response.status_code == 200
        assert response.json()["total"] >= 1


@pytestmark_docker
class TestGetTrial:
    def test_get_by_id(self, client, db_session):
        trial, _, _, _ = _seed_trial(db_session)
        response = client.get(f"/api/v1/trials/{trial.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["nct_id"] == trial.nct_id
        assert data["official_title"] is not None
        assert data["conditions"] == ["Breast Cancer"]
        assert data["sponsor"] == "Test Sponsor"
        assert "criteria_summary" in data
        assert data["criteria_summary"]["total"] == 2
        assert data["criteria_summary"]["review_pending"] == 1

    def test_get_by_id_not_found(self, client):
        fake_id = uuid.uuid4()
        response = client.get(f"/api/v1/trials/{fake_id}")
        assert response.status_code == 404

    def test_get_by_nct_id(self, client, db_session):
        _seed_trial(db_session, nct_id="NCT99887766")
        response = client.get("/api/v1/trials/nct/NCT99887766")
        assert response.status_code == 200
        data = response.json()
        assert data["nct_id"] == "NCT99887766"
        assert "criteria_summary" in data

    def test_get_by_nct_id_not_found(self, client):
        response = client.get("/api/v1/trials/nct/NCT00000000")
        assert response.status_code == 404

    def test_trial_timestamps_are_timezone_aware_utc(self, client, db_session):
        trial, _, _, _ = _seed_trial(db_session)
        response = client.get(f"/api/v1/trials/{trial.id}")
        assert response.status_code == 200
        parsed = _parse_api_datetime(response.json()["ingested_at"])
        assert parsed.tzinfo is not None
        assert parsed.utcoffset().total_seconds() == 0

    def test_trial_summary_uses_latest_completed_run_only(self, client, db_session):
        trial, _, _, _ = _seed_trial(db_session)
        _add_completed_run(
            db_session,
            trial,
            [
                {
                    "type": "inclusion",
                    "category": "line_of_therapy",
                    "original_text": "Failed at least 1 prior line of systemic therapy",
                    "operator": "gte",
                    "value_low": 1,
                }
            ],
        )

        response = client.get(f"/api/v1/trials/{trial.id}")
        assert response.status_code == 200
        assert response.json()["criteria_summary"]["total"] == 1


@pytestmark_docker
class TestSearchIngestEndpoint:
    def test_search_ingest_reports_attempted_skipped_and_failed(self, client):
        success_trial = Trial(id=uuid.uuid4(), nct_id="NCTGOOD001")
        skipped_trial = Trial(id=uuid.uuid4(), nct_id="NCTSKIP001")
        service_results = [
            SearchIngestTrialResult(
                nct_id="NCTGOOD001",
                trial=success_trial,
                criteria_count=5,
            ),
            SearchIngestTrialResult(
                nct_id="NCTSKIP001",
                trial=skipped_trial,
                skipped=True,
            ),
            SearchIngestTrialResult(
                nct_id="NCTFAIL001",
                error_message="boom",
            ),
            SearchIngestTrialResult(
                nct_id=None,
                error_message="Search result missing NCT ID",
            ),
        ]

        with patch("app.api.routes.trials.IngestionService.search_and_ingest", return_value=service_results):
            response = client.post(
                "/api/v1/trials/search-ingest",
                json={"condition": "breast cancer", "limit": 4},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["attempted"] == 4
        assert data["ingested"] == 1
        assert data["skipped"] == 1
        assert data["failed"] == 2
        assert data["trials"][0]["status"] == "ingested"
        assert data["trials"][0]["trial_id"] == str(success_trial.id)
        assert data["trials"][1]["status"] == "skipped"
        assert data["trials"][1]["trial_id"] == str(skipped_trial.id)
        assert data["trials"][2]["status"] == "failed"
        assert data["trials"][2]["error_message"] == "boom"
        assert data["trials"][3]["nct_id"] is None
        assert data["trials"][3]["error_message"] == "Search result missing NCT ID"


@pytestmark_docker
class TestGetCriteria:
    def test_get_trial_criteria(self, client, db_session):
        trial, _, c1, c2 = _seed_trial(db_session)
        response = client.get(f"/api/v1/trials/{trial.id}/criteria")
        assert response.status_code == 200
        data = response.json()
        assert len(data["criteria"]) == 2
        categories = {c["category"] for c in data["criteria"]}
        assert "age" in categories
        assert "cns_metastases" in categories

    def test_filter_by_type(self, client, db_session):
        trial, _, _, _ = _seed_trial(db_session)
        response = client.get(f"/api/v1/trials/{trial.id}/criteria?type=inclusion")
        assert response.status_code == 200
        for c in response.json()["criteria"]:
            assert c["type"] == "inclusion"

    def test_filter_by_category(self, client, db_session):
        trial, _, _, _ = _seed_trial(db_session)
        response = client.get(f"/api/v1/trials/{trial.id}/criteria?category=age")
        assert response.status_code == 200
        assert len(response.json()["criteria"]) == 1
        assert response.json()["criteria"][0]["category"] == "age"

    def test_filter_by_review_required(self, client, db_session):
        trial, _, _, _ = _seed_trial(db_session)
        response = client.get(f"/api/v1/trials/{trial.id}/criteria?review_required=true")
        assert response.status_code == 200
        for c in response.json()["criteria"]:
            assert c["review_required"] is True

    def test_get_single_criterion(self, client, db_session):
        _, _, c1, _ = _seed_trial(db_session)
        response = client.get(f"/api/v1/criteria/{c1.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "age"
        assert data["operator"] == "gte"
        assert data["value_low"] == 18
        assert data["unit"] == "years"
        assert data["negated"] is False

    def test_get_criterion_not_found(self, client):
        response = client.get(f"/api/v1/criteria/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_criteria_route_returns_latest_completed_run_only(self, client, db_session):
        trial, _, _, _ = _seed_trial(db_session)
        _add_completed_run(
            db_session,
            trial,
            [
                {
                    "type": "inclusion",
                    "category": "line_of_therapy",
                    "original_text": "Failed at least 1 prior line of systemic therapy",
                    "operator": "gte",
                    "value_low": 1,
                }
            ],
        )

        response = client.get(f"/api/v1/trials/{trial.id}/criteria")
        assert response.status_code == 200
        data = response.json()
        assert len(data["criteria"]) == 1
        assert data["criteria"][0]["category"] == "line_of_therapy"
        assert "pipeline_run_id" in data["criteria"][0]
        assert "raw_expression" in data["criteria"][0]


@pytestmark_docker
class TestFHIRExport:
    def test_fhir_export(self, client, db_session):
        trial, _, _, _ = _seed_trial(db_session)
        response = client.get(f"/api/v1/trials/{trial.id}/fhir")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/fhir+json"
        data = response.json()
        assert data["resourceType"] == "ResearchStudy"
        assert data["identifier"][0]["value"] == trial.nct_id
        assert data["status"] == "active"
        assert "phase" in data
        assert "extension" in data

    def test_fhir_not_found(self, client):
        response = client.get(f"/api/v1/trials/{uuid.uuid4()}/fhir")
        assert response.status_code == 404

    def test_fhir_export_uses_latest_completed_run_only(self, client, db_session):
        trial, _, _, _ = _seed_trial(db_session)
        _add_completed_run(
            db_session,
            trial,
            [
                {
                    "type": "inclusion",
                    "category": "line_of_therapy",
                    "original_text": "Failed at least 1 prior line of systemic therapy",
                    "operator": "gte",
                    "value_low": 1,
                }
            ],
        )

        response = client.get(f"/api/v1/trials/{trial.id}/fhir")
        assert response.status_code == 200
        rendered_text = json.dumps(response.json())
        assert "Failed at least 1 prior line of systemic therapy" in rendered_text
        assert "Age >= 18 years" not in rendered_text


@pytestmark_docker
class TestReviewQueue:
    def test_review_queue_returns_pending(self, client, db_session):
        _seed_trial(db_session)
        response = client.get("/api/v1/review")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "breakdown_by_reason" in data
        assert data["total"] >= 1
        for item in data["items"]:
            assert item["review_required"] is True
            assert item["review_status"] == "pending"

    def test_review_filter_by_reason(self, client, db_session):
        _seed_trial(db_session)
        response = client.get("/api/v1/review?reason=fuzzy_match")
        assert response.status_code == 200
        for item in response.json()["items"]:
            assert item["review_reason"] == "fuzzy_match"

    def test_review_filter_by_trial_id(self, client, db_session):
        trial, _, _, _ = _seed_trial(db_session)
        response = client.get(f"/api/v1/review?trial_id={trial.id}")
        assert response.status_code == 200
        for item in response.json()["items"]:
            assert item["trial_id"] == str(trial.id)

    def test_review_breakdown_by_reason(self, client, db_session):
        _seed_trial(db_session)
        response = client.get("/api/v1/review")
        data = response.json()
        assert "fuzzy_match" in data["breakdown_by_reason"]
        assert data["breakdown_by_reason"]["fuzzy_match"] >= 1

    def test_review_queue_ignores_pending_items_from_superseded_runs(self, client, db_session):
        trial, _, _, _ = _seed_trial(db_session)
        _add_completed_run(
            db_session,
            trial,
            [
                {
                    "type": "inclusion",
                    "category": "line_of_therapy",
                    "original_text": "Failed at least 1 prior line of systemic therapy",
                    "operator": "gte",
                    "value_low": 1,
                }
            ],
        )

        response = client.get(f"/api/v1/review?trial_id={trial.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["breakdown_by_reason"] == {}


@pytestmark_docker
class TestPipelineEndpoints:
    def test_pipeline_status(self, client, db_session):
        _seed_trial(db_session)
        response = client.get("/api/v1/pipeline/status")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "total_runs" in data
        assert "completed" in data
        assert "failed" in data
        assert "total_trials" in data
        assert "total_criteria" in data
        assert "review_pending" in data
        assert data["total_runs"] >= 1
        assert data["total_trials"] >= 1
        assert data["total_criteria"] >= 1

    def test_pipeline_status_counts_latest_run_criteria_only(self, client, db_session):
        trial, _, _, _ = _seed_trial(db_session)
        baseline = client.get("/api/v1/pipeline/status")
        assert baseline.status_code == 200
        baseline_data = baseline.json()
        _add_completed_run(
            db_session,
            trial,
            [
                {
                    "type": "inclusion",
                    "category": "line_of_therapy",
                    "original_text": "Failed at least 1 prior line of systemic therapy",
                    "operator": "gte",
                    "value_low": 1,
                }
            ],
        )

        response = client.get("/api/v1/pipeline/status")
        assert response.status_code == 200
        data = response.json()
        assert data["total_runs"] == baseline_data["total_runs"] + 1
        assert data["completed"] == baseline_data["completed"] + 1
        assert data["total_trials"] == baseline_data["total_trials"]
        assert data["total_criteria"] == baseline_data["total_criteria"] - 1
        assert data["review_pending"] == baseline_data["review_pending"] - 1

    def test_list_pipeline_runs(self, client, db_session):
        _seed_trial(db_session)
        response = client.get("/api/v1/pipeline/runs")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) >= 1
        run = data["items"][0]
        assert "id" in run
        assert "pipeline_version" in run
        assert "status" in run
        assert "criteria_extracted_count" in run
        assert "diff_summary" in run

    def test_list_pipeline_runs_filter_by_trial(self, client, db_session):
        trial, run, _, _ = _seed_trial(db_session)
        response = client.get(f"/api/v1/pipeline/runs?trial_id={trial.id}")
        assert response.status_code == 200
        for item in response.json()["items"]:
            assert item["trial_id"] == str(trial.id)

    def test_list_pipeline_runs_filter_by_status(self, client, db_session):
        _seed_trial(db_session)
        response = client.get("/api/v1/pipeline/runs?status=completed")
        assert response.status_code == 200
        for item in response.json()["items"]:
            assert item["status"] == "completed"

    def test_list_pipeline_runs_filter_by_version(self, client, db_session):
        _seed_trial(db_session)
        response = client.get("/api/v1/pipeline/runs?pipeline_version=0.1.0")
        assert response.status_code == 200
        for item in response.json()["items"]:
            assert item["pipeline_version"] == "0.1.0"

    def test_get_pipeline_run(self, client, db_session):
        _, run, _, _ = _seed_trial(db_session)
        response = client.get(f"/api/v1/pipeline/runs/{run.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["pipeline_version"] == "0.1.0"

    def test_get_pipeline_run_not_found(self, client):
        response = client.get(f"/api/v1/pipeline/runs/{uuid.uuid4()}")
        assert response.status_code == 404


@pytestmark_docker
class TestReExtract:
    def test_re_extract_reruns_pipeline(self, client, db_session):
        trial, _, _, _ = _seed_trial(db_session)
        response = client.post(f"/api/v1/trials/{trial.id}/re-extract")
        assert response.status_code == 200
        data = response.json()
        assert data["trial_id"] == str(trial.id)
        assert "criteria_count" in data
        assert "review_count" in data
        assert "diff_summary" in data
        assert "added" in data["diff_summary"]
        assert "removed" in data["diff_summary"]

        # Verify a new pipeline run was created
        runs = db_session.query(PipelineRun).filter_by(trial_id=trial.id).count()
        assert runs == 2  # original + re-extract

    def test_re_extract_not_found(self, client):
        response = client.post(f"/api/v1/trials/{uuid.uuid4()}/re-extract")
        assert response.status_code == 404


@pytestmark_docker
class TestIngestEndpoint:
    def test_ingest_via_api(self, client):
        mock_response = json.loads((MOCK_DIR / "NCT04567890.json").read_text())
        # Use unique NCT ID
        unique_nct = f"NCT{uuid.uuid4().hex[:8].upper()}"
        mock_response["protocolSection"]["identificationModule"]["nctId"] = unique_nct
        with patch("app.ingestion.ctgov_client.CTGovClient.fetch_study", return_value=mock_response):
            response = client.post("/api/v1/trials/ingest", json={"nct_id": unique_nct})
        assert response.status_code == 201
        data = response.json()
        assert data["nct_id"] == unique_nct
        assert "trial_id" in data
        assert "criteria_count" in data
