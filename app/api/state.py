from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.matching.service import CriterionEvaluation
    from app.models.database import ExtractedCriterion, MatchResult, MatchResultCriterion

LOW_CONFIDENCE_THRESHOLD = 0.5
UNSPECIFIED_REVIEW_REASON = "unspecified_review_reason"


def criterion_state_from_extracted(criterion: ExtractedCriterion) -> tuple[str, str | None]:
    if criterion.review_status == "rejected":
        return "blocked_unsupported", "rejected"
    if criterion.review_status in {"accepted", "corrected"}:
        return "structured_safe", None
    if criterion.review_required:
        reason = criterion.review_reason or UNSPECIFIED_REVIEW_REASON
        return "review_required", f"review_required:{reason}"
    if (criterion.confidence or 0.0) < LOW_CONFIDENCE_THRESHOLD:
        return "structured_low_confidence", "low_confidence"
    return "structured_safe", None


def criterion_state_from_evaluation(evaluation: CriterionEvaluation) -> tuple[str, str | None]:
    return evaluation.state, evaluation.state_reason


def criterion_state_from_match_result_criterion(criterion: MatchResultCriterion) -> tuple[str, str | None]:
    return criterion.state, criterion.state_reason


def match_state_from_evaluations(evaluations: list[CriterionEvaluation]) -> tuple[str, str | None]:
    states = [criterion_state_from_evaluation(evaluation)[0] for evaluation in evaluations]
    if "review_required" in states:
        return "review_required", "review_required"
    if "blocked_unsupported" in states:
        return "blocked_unsupported", "blocked_unsupported"
    if "structured_low_confidence" in states:
        return "structured_low_confidence", "low_confidence"
    return "structured_safe", None


def match_state_from_match_result(match_result: MatchResult) -> tuple[str, str | None]:
    return match_result.state, match_result.state_reason
