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


def test_create_trial(db_session):
    trial = Trial(
        nct_id="NCT00000001",
        raw_json={"test": True},
        content_hash="abc123",
        brief_title="Test Trial",
        status="RECRUITING",
    )
    db_session.add(trial)
    db_session.flush()
    assert trial.id is not None
    assert trial.extraction_status == "pending"


def test_create_pipeline_run_and_criterion(db_session):
    trial = Trial(
        nct_id="NCT00000002",
        raw_json={"test": True},
        content_hash="def456",
        brief_title="Test Trial 2",
        status="RECRUITING",
    )
    db_session.add(trial)
    db_session.flush()

    run = PipelineRun(
        trial_id=trial.id,
        pipeline_version="0.1.1",
        input_hash="hash123",
        input_snapshot={"test": True},
    )
    db_session.add(run)
    db_session.flush()

    criterion = ExtractedCriterion(
        trial_id=trial.id,
        type="inclusion",
        category="age",
        original_text="Age >= 18 years",
        operator="gte",
        value_low=18,
        unit="years",
        confidence=0.95,
        pipeline_version="0.1.1",
        pipeline_run_id=run.id,
    )
    db_session.add(criterion)
    db_session.flush()
    assert criterion.id is not None
    assert criterion.negated is False
    assert criterion.review_required is False
