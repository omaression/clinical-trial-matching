import uuid
from datetime import datetime

import docker
import pytest

from app.models.database import ExtractedCriterion, PipelineRun, Trial


def _docker_available():
    try:
        docker.from_env().ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _docker_available(), reason="Docker not available")


def _parse_api_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.fixture
def seeded_criterion(db_session):
    unique_nct = f"NCT{uuid.uuid4().hex[:8].upper()}"
    trial = Trial(
        nct_id=unique_nct, raw_json={}, content_hash="test",
        brief_title="Review Test", status="RECRUITING",
    )
    db_session.add(trial)
    db_session.flush()

    run = PipelineRun(
        trial_id=trial.id, pipeline_version="0.1.2",
        input_hash="test", input_snapshot={}, status="completed",
    )
    db_session.add(run)
    db_session.flush()

    criterion = ExtractedCriterion(
        trial_id=trial.id, type="inclusion", category="diagnosis",
        original_text="Prior TNBC diagnosis", parse_status="parsed",
        confidence=0.60, review_required=True, review_reason="fuzzy_match",
        review_status="pending", coded_concepts=[
            {"system": "mesh", "code": "D000073182",
             "display": "Triple Negative Breast Neoplasms", "match_type": "fuzzy"}
        ],
        pipeline_version="0.1.2", pipeline_run_id=run.id,
    )
    db_session.add(criterion)
    db_session.commit()
    return criterion


@pytest.fixture
def superseded_criterion(db_session):
    unique_nct = f"NCT{uuid.uuid4().hex[:8].upper()}"
    trial = Trial(
        nct_id=unique_nct, raw_json={}, content_hash="test",
        brief_title="Superseded Review Test", status="RECRUITING",
    )
    db_session.add(trial)
    db_session.flush()

    old_run = PipelineRun(
        trial_id=trial.id, pipeline_version="0.1.2",
        input_hash="old", input_snapshot={}, status="completed",
    )
    db_session.add(old_run)
    db_session.flush()

    criterion = ExtractedCriterion(
        trial_id=trial.id, type="inclusion", category="diagnosis",
        original_text="Prior TNBC diagnosis", parse_status="parsed",
        confidence=0.60, review_required=True, review_reason="fuzzy_match",
        review_status="pending", coded_concepts=[],
        pipeline_version="0.1.2", pipeline_run_id=old_run.id,
    )
    db_session.add(criterion)
    db_session.flush()

    latest_run = PipelineRun(
        trial_id=trial.id, pipeline_version="0.1.2",
        input_hash="new", input_snapshot={}, status="completed",
    )
    db_session.add(latest_run)
    db_session.commit()
    return criterion


@pytest.fixture
def seeded_logic_group_criterion(db_session):
    unique_nct = f"NCT{uuid.uuid4().hex[:8].upper()}"
    trial = Trial(
        nct_id=unique_nct, raw_json={}, content_hash="test",
        brief_title="Logic Group Review Test", status="RECRUITING",
    )
    db_session.add(trial)
    db_session.flush()

    run = PipelineRun(
        trial_id=trial.id, pipeline_version="0.1.2",
        input_hash="test", input_snapshot={}, status="completed",
    )
    db_session.add(run)
    db_session.flush()

    logic_group_id = uuid.uuid4()
    criterion = ExtractedCriterion(
        trial_id=trial.id, type="inclusion", category="diagnosis",
        original_text="Melanoma or breast cancer", parse_status="parsed",
        logic_group_id=logic_group_id, logic_operator="OR",
        confidence=0.60, review_required=True, review_reason="fuzzy_match",
        review_status="pending", coded_concepts=[],
        original_extracted={"source_sentence": "Has melanoma or breast cancer"},
        pipeline_version="0.1.2", pipeline_run_id=run.id,
    )
    db_session.add(criterion)
    db_session.commit()
    return criterion


class TestAccept:
    def test_accept_clears_review(self, client, seeded_criterion):
        response = client.patch(
            f"/api/v1/criteria/{seeded_criterion.id}/review",
            json={"action": "accept", "reviewed_by": "dr_smith"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["review_status"] == "accepted"
        assert data["review_required"] is False
        parsed = _parse_api_datetime(data["reviewed_at"])
        assert parsed.tzinfo is not None
        assert parsed.utcoffset().total_seconds() == 0

    def test_cannot_review_already_resolved_criterion(self, client, seeded_criterion):
        first = client.patch(
            f"/api/v1/criteria/{seeded_criterion.id}/review",
            json={"action": "accept", "reviewed_by": "dr_smith"},
        )
        assert first.status_code == 200

        second = client.patch(
            f"/api/v1/criteria/{seeded_criterion.id}/review",
            json={"action": "reject", "reviewed_by": "dr_jones"},
        )
        assert second.status_code == 409
        assert second.json()["detail"] == "Criterion review has already been resolved"


class TestCorrect:
    def test_correct_snapshots_original(self, client, seeded_criterion):
        response = client.patch(
            f"/api/v1/criteria/{seeded_criterion.id}/review",
            json={
                "action": "correct",
                "reviewed_by": "dr_smith",
                "review_notes": "Confirmed TNBC via chart review",
                "corrected_data": {
                    "coded_concepts": [
                        {"system": "mesh", "code": "D000073182",
                         "display": "Triple Negative Breast Neoplasms", "match_type": "exact"}
                    ],
                    "confidence": 1.0,
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["review_status"] == "corrected"
        assert data["confidence"] == 1.0
        assert data["original_extracted"] is not None
        assert data["original_extracted"]["type"] == "inclusion"
        assert data["original_extracted"]["parse_status"] == "parsed"
        assert data["original_extracted"]["negated"] is False

    def test_correct_rejects_non_editable_fields(self, client, seeded_criterion):
        response = client.patch(
            f"/api/v1/criteria/{seeded_criterion.id}/review",
            json={
                "action": "correct",
                "reviewed_by": "dr_smith",
                "corrected_data": {
                    "review_status": "accepted",
                },
            },
        )
        assert response.status_code == 422

    def test_cannot_review_superseded_criterion(self, client, superseded_criterion):
        response = client.patch(
            f"/api/v1/criteria/{superseded_criterion.id}/review",
            json={
                "action": "accept",
                "reviewed_by": "dr_smith",
            },
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "Criterion belongs to a superseded pipeline run and cannot be reviewed"

    def test_correct_serializes_logic_group_id_in_snapshot(self, client, seeded_logic_group_criterion):
        response = client.patch(
            f"/api/v1/criteria/{seeded_logic_group_criterion.id}/review",
            json={
                "action": "correct",
                "reviewed_by": "dr_smith",
                "corrected_data": {
                    "confidence": 0.9,
                },
            },
        )
        assert response.status_code == 200
        assert response.json()["original_extracted"]["logic_group_id"] == str(
            seeded_logic_group_criterion.logic_group_id
        )
        assert response.json()["original_extracted"]["source_sentence"] == "Has melanoma or breast cancer"


class TestReject:
    def test_reject_marks_rejected(self, client, seeded_criterion):
        response = client.patch(
            f"/api/v1/criteria/{seeded_criterion.id}/review",
            json={
                "action": "reject",
                "reviewed_by": "dr_smith",
                "review_notes": "False positive extraction",
            },
        )
        assert response.status_code == 200
        assert response.json()["review_status"] == "rejected"
