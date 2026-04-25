from types import SimpleNamespace

from app.api.state import criterion_state_from_extracted


def _criterion(**overrides):
    payload = {
        "review_required": False,
        "review_reason": None,
        "review_status": None,
        "confidence": 0.9,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_terminal_review_status_overrides_review_required_flag_for_accepted_rows():
    state, reason = criterion_state_from_extracted(
        _criterion(review_required=True, review_reason="fuzzy_match", review_status="accepted")
    )

    assert state == "structured_safe"
    assert reason is None


def test_terminal_review_status_overrides_review_required_flag_for_rejected_rows():
    state, reason = criterion_state_from_extracted(
        _criterion(review_required=True, review_reason="fuzzy_match", review_status="rejected")
    )

    assert state == "blocked_unsupported"
    assert reason == "rejected"
