import json
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


@pytest.fixture
def mock_ctgov_response():
    return json.loads((MOCK_DIR / "NCT04567890.json").read_text())


@pytest.fixture
def service(db_session):
    return IngestionService(db_session)


class TestIngestSingleTrial:
    def test_ingests_and_extracts(self, service, db_session, mock_ctgov_response):
        with patch.object(service._client, "fetch_study", return_value=mock_ctgov_response):
            result = service.ingest("NCT04567890")

        assert result.trial.nct_id == "NCT04567890"
        assert result.trial.extraction_status == "completed"
        assert result.criteria_count > 0

        trial = db_session.query(Trial).filter_by(nct_id="NCT04567890").first()
        assert trial is not None
        run = db_session.query(PipelineRun).filter_by(trial_id=trial.id).first()
        assert run is not None
        assert run.status == "completed"
        assert run.input_snapshot is not None


class TestIdempotency:
    def test_reingest_unchanged_skips(self, service, db_session, mock_ctgov_response):
        with patch.object(service._client, "fetch_study", return_value=mock_ctgov_response):
            result1 = service.ingest("NCT04567890")
            result2 = service.ingest("NCT04567890")

        assert result2.skipped is True
        runs = db_session.query(PipelineRun).filter_by(trial_id=result1.trial.id).count()
        assert runs == 1

    def test_reingest_changed_reextracts(self, service, db_session, mock_ctgov_response):
        with patch.object(service._client, "fetch_study", return_value=mock_ctgov_response):
            result1 = service.ingest("NCT04567890")

        changed = json.loads(json.dumps(mock_ctgov_response))
        changed["protocolSection"]["eligibilityModule"]["eligibilityCriteria"] = "Age >= 21 years"
        with patch.object(service._client, "fetch_study", return_value=changed):
            result2 = service.ingest("NCT04567890")

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
