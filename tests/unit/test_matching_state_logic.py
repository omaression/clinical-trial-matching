import uuid

from app.matching.service import CriterionEvaluation, _collapse_or_group


def _evaluation(
    *,
    criterion_type: str,
    outcome: str,
    state: str,
    state_reason: str | None = None,
) -> CriterionEvaluation:
    return CriterionEvaluation(
        criterion_id=None,
        pipeline_run_id=None,
        logic_group_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        logic_operator="OR",
        source_type="extracted",
        source_label="LLM extraction",
        criterion_type=criterion_type,
        category="diagnosis",
        criterion_text="Test criterion",
        outcome=outcome,
        state=state,
        state_reason=state_reason,
        explanation_text="",
        explanation_type="",
        evidence_payload=None,
    )


def test_collapse_or_group_keeps_safe_state_when_safe_branch_matches():
    collapsed = _collapse_or_group(
        [
            _evaluation(criterion_type="inclusion", outcome="matched", state="structured_safe"),
            _evaluation(
                criterion_type="inclusion",
                outcome="matched",
                state="structured_low_confidence",
                state_reason="low_confidence",
            ),
            _evaluation(
                criterion_type="inclusion",
                outcome="not_matched",
                state="structured_low_confidence",
                state_reason="low_confidence",
            ),
        ]
    )

    assert collapsed.outcome == "matched"
    assert collapsed.state == "structured_safe"
    assert collapsed.state_reason is None


def test_collapse_or_group_propagates_low_confidence_when_all_inclusion_branches_fail():
    collapsed = _collapse_or_group(
        [
            _evaluation(criterion_type="inclusion", outcome="not_matched", state="structured_safe"),
            _evaluation(
                criterion_type="inclusion",
                outcome="not_matched",
                state="structured_low_confidence",
                state_reason="low_confidence",
            ),
        ]
    )

    assert collapsed.outcome == "not_matched"
    assert collapsed.state == "structured_low_confidence"
    assert collapsed.state_reason == "low_confidence"


def test_collapse_or_group_propagates_low_confidence_when_all_exclusion_branches_clear():
    collapsed = _collapse_or_group(
        [
            _evaluation(criterion_type="exclusion", outcome="not_triggered", state="structured_safe"),
            _evaluation(
                criterion_type="exclusion",
                outcome="not_triggered",
                state="structured_low_confidence",
                state_reason="low_confidence",
            ),
        ]
    )

    assert collapsed.outcome == "not_triggered"
    assert collapsed.state == "structured_low_confidence"
    assert collapsed.state_reason == "low_confidence"


def test_collapse_or_group_propagates_blocked_state_for_unknown_outcomes():
    collapsed = _collapse_or_group(
        [
            _evaluation(criterion_type="inclusion", outcome="unknown", state="structured_safe"),
            _evaluation(
                criterion_type="inclusion",
                outcome="unknown",
                state="blocked_unsupported",
                state_reason="rejected",
            ),
        ]
    )

    assert collapsed.outcome == "unknown"
    assert collapsed.state == "blocked_unsupported"
    assert collapsed.state_reason == "blocked_unsupported"


def test_collapse_or_group_propagates_nonwinning_low_confidence_into_unknown_state():
    collapsed = _collapse_or_group(
        [
            _evaluation(criterion_type="inclusion", outcome="unknown", state="structured_safe"),
            _evaluation(
                criterion_type="inclusion",
                outcome="not_matched",
                state="structured_low_confidence",
                state_reason="low_confidence",
            ),
        ]
    )

    assert collapsed.outcome == "unknown"
    assert collapsed.state == "structured_low_confidence"
    assert collapsed.state_reason == "low_confidence"


def test_collapse_or_group_preserves_safe_state_for_matched_branch_despite_hidden_review_member():
    collapsed = _collapse_or_group(
        [
            _evaluation(criterion_type="inclusion", outcome="matched", state="structured_safe"),
            _evaluation(
                criterion_type="inclusion",
                outcome="requires_review",
                state="review_required",
                state_reason="review_required:fuzzy_match",
            ),
        ]
    )

    assert collapsed.outcome == "matched"
    assert collapsed.state == "structured_safe"
    assert collapsed.state_reason is None
