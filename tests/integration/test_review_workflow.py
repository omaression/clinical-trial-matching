import docker
import pytest
from app.models.database import Trial, PipelineRun, ExtractedCriterion


def _docker_available():
    try:
        docker.from_env().ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _docker_available(), reason="Docker not available")


@pytest.fixture
def seeded_criterion(db_session):
    trial = Trial(
        nct_id="NCT99999999", raw_json={}, content_hash="test",
        brief_title="Review Test", status="RECRUITING",
    )
    db_session.add(trial)
    db_session.flush()

    run = PipelineRun(
        trial_id=trial.id, pipeline_version="0.1.0",
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
        pipeline_version="0.1.0", pipeline_run_id=run.id,
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
