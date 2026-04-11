import copy
import json
import uuid

import docker
import pytest
from pathlib import Path
from unittest.mock import patch

from app.ingestion.service import IngestionService
from app.ingestion.hasher import content_hash
from app.models.database import Trial, PipelineRun, ExtractedCriterion

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


class TestContentHash:
    def test_hash_deterministic(self):
        h1 = content_hash("some eligibility text")
        h2 = content_hash("some eligibility text")
        assert h1 == h2

    def test_hash_differs_on_change(self):
        h1 = content_hash("Age >= 18")
        h2 = content_hash("Age >= 21")
        assert h1 != h2
