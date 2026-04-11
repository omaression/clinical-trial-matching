import json
import uuid
from pathlib import Path
from unittest.mock import patch

import docker
import pytest

from app.models.database import ExtractedCriterion, PipelineRun, Trial

MOCK_DIR = Path(__file__).parent.parent / "fixtures" / "mock_ctgov_responses"


def _docker_available():
    try:
        docker.from_env().ping()
        return True
    except Exception:
        return False


# --- Non-DB tests (no Docker needed) ---


class TestHealthEndpoint:
    def test_health(self):
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as c:
            response = c.get("/api/v1/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "pipeline_version" in data


class TestRouteRegistration:
    def test_openapi_schema_available(self):
        from fastapi.testclient import TestClient
        from app.main import app

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


def _seed_trial(db_session, nct_id=None):
    """Helper to insert a trial with a pipeline run and criteria."""
    nct_id = nct_id or f"NCT{uuid.uuid4().hex[:8].upper()}"
    trial = Trial(
        nct_id=nct_id,
        raw_json={"protocolSection": {"eligibilityModule": {"eligibilityCriteria": "Age >= 18"}}},
        content_hash="test_hash",
        brief_title=f"Test Trial {nct_id}",
        official_title=f"Official Title for {nct_id}",
        status="RECRUITING",
        phase="PHASE3",
        conditions=["Breast Cancer"],
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
        _seed_trial(db_session)
        response = client.get("/api/v1/trials?status=RECRUITING")
        assert response.status_code == 200
        for item in response.json()["items"]:
            assert item["status"] == "RECRUITING"


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

    def test_get_by_id_not_found(self, client):
        fake_id = uuid.uuid4()
        response = client.get(f"/api/v1/trials/{fake_id}")
        assert response.status_code == 404

    def test_get_by_nct_id(self, client, db_session):
        trial, _, _, _ = _seed_trial(db_session, nct_id="NCT99887766")
        response = client.get("/api/v1/trials/nct/NCT99887766")
        assert response.status_code == 200
        assert response.json()["nct_id"] == "NCT99887766"

    def test_get_by_nct_id_not_found(self, client):
        response = client.get("/api/v1/trials/nct/NCT00000000")
        assert response.status_code == 404


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


@pytestmark_docker
class TestFHIRExport:
    def test_fhir_export(self, client, db_session):
        trial, _, _, _ = _seed_trial(db_session)
        response = client.get(f"/api/v1/trials/{trial.id}/fhir")
        assert response.status_code == 200
        data = response.json()
        assert data["resourceType"] == "ResearchStudy"
        assert data["identifier"][0]["value"] == trial.nct_id
        assert data["status"] == "active"
        assert "phase" in data
        assert "extension" in data

    def test_fhir_not_found(self, client):
        response = client.get(f"/api/v1/trials/{uuid.uuid4()}/fhir")
        assert response.status_code == 404


@pytestmark_docker
class TestReviewQueue:
    def test_review_queue_returns_pending(self, client, db_session):
        _seed_trial(db_session)
        response = client.get("/api/v1/review")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        # Our seeded data has 1 review-required criterion
        assert data["total"] >= 1
        for item in data["items"]:
            assert item["review_required"] is True
            assert item["review_status"] == "pending"


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
        assert data["total_runs"] >= 1

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
        with patch("app.ingestion.ctgov_client.CTGovClient.fetch_study", return_value=mock_response):
            response = client.post("/api/v1/trials/ingest", json={"nct_id": "NCT04567890"})
        assert response.status_code == 201
        data = response.json()
        assert data["nct_id"] == "NCT04567890"
        assert "trial_id" in data
        assert "criteria_count" in data
