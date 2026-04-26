from types import SimpleNamespace

from app.api.schemas import MatchGapReportResponse
from app.matching.gap_report import build_gap_report_payload


def _criterion(**overrides):
    payload = {
        "criterion_id": None,
        "pipeline_run_id": None,
        "source_label": "criterion",
        "criterion_type": "inclusion",
        "explanation_type": "criterion_unknown",
        "outcome": "unknown",
        "state": "structured_safe",
        "state_reason": None,
        "source_type": "extracted",
        "category": "diagnosis",
        "criterion_text": "Test criterion",
        "explanation_text": "Available patient data is insufficient to evaluate this criterion safely.",
        "evidence_payload": {"patient_conditions": []},
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_gap_report_prioritizes_review_required_state_for_collapsed_unknowns():
    report = MatchGapReportResponse.model_validate(build_gap_report_payload(
        [
            _criterion(
                outcome="unknown",
                state="review_required",
                state_reason="review_required",
                evidence_payload={
                    "logic_group_id": "11111111-1111-1111-1111-111111111111",
                    "logic_operator": "OR",
                    "member_outcomes": ["unknown", "not_matched"],
                    "member_states": ["review_required", "structured_safe"],
                },
            )
        ]
    ))

    assert report.review_required[0].criterion_text == "Test criterion"
    assert report.missing_data == []
    assert report.hard_blockers == []
    assert report.clarifiable_blockers == []


def test_gap_report_keeps_low_confidence_extracted_sex_blockers_clarifiable():
    report = MatchGapReportResponse.model_validate(build_gap_report_payload(
        [
            _criterion(
                outcome="not_matched",
                state="structured_low_confidence",
                state_reason="low_confidence",
                category="sex",
                criterion_text="Male patients only",
                evidence_payload={"patient_sex": "female"},
            )
        ]
    ))

    assert report.hard_blockers == []
    assert len(report.clarifiable_blockers) == 1
    assert report.clarifiable_blockers[0].category == "sex"


def test_gap_report_does_not_relabel_legacy_unverifiable_unknowns_as_missing_data():
    report = MatchGapReportResponse.model_validate(build_gap_report_payload(
        [
            _criterion(
                outcome="unknown",
                state="structured_low_confidence",
                state_reason="legacy_state_unverifiable",
                evidence_payload={"patient_conditions": []},
            )
        ]
    ))

    assert report.missing_data == []
    assert len(report.review_required) == 1
    assert report.review_required[0].state_reason == "legacy_state_unverifiable"


def test_gap_report_preserves_requires_review_for_grouped_rows_with_snapshot_metadata():
    report = MatchGapReportResponse.model_validate(build_gap_report_payload(
        [
            _criterion(
                outcome="requires_review",
                state="review_required",
                state_reason="review_required:fuzzy_match",
                evidence_payload={
                    "review_reason": "fuzzy_match",
                    "review_status": "pending",
                    "snapshot_match_metadata": {
                        "logic_group_id": "11111111-1111-1111-1111-111111111111",
                        "logic_operator": "OR",
                    },
                },
            )
        ]
    ))

    assert len(report.review_required) == 1
    assert report.review_required[0].state_reason == "review_required"


def test_gap_report_routes_ambiguous_unknowns_to_review_required_not_missing_data():
    report = MatchGapReportResponse.model_validate(build_gap_report_payload(
        [
            _criterion(
                outcome="unknown",
                state="structured_low_confidence",
                state_reason="low_confidence",
                category="sex",
                criterion_text="Participants of the appropriate sex may enroll",
                evidence_payload={"patient_sex": "female"},
                explanation_text="Available patient data is insufficient to evaluate this criterion safely.",
            )
        ]
    ))

    assert report.missing_data == []
    assert len(report.review_required) == 1
    assert report.review_required[0].category == "sex"


def test_gap_report_routes_low_confidence_favorable_outcomes_to_review_required():
    report = MatchGapReportResponse.model_validate(build_gap_report_payload(
        [
            _criterion(
                outcome="matched",
                state="structured_low_confidence",
                state_reason="low_confidence",
                category="diagnosis",
                criterion_text="Metastatic breast cancer",
                evidence_payload={"patient_conditions": [{"description": "Metastatic breast cancer"}]},
            )
        ]
    ))

    assert report.clarifiable_blockers == []
    assert len(report.review_required) == 1
    assert report.review_required[0].outcome == "matched"


def test_grouped_or_unknown_preserves_review_required_signal_over_missing_data():
    report = MatchGapReportResponse.model_validate(build_gap_report_payload(
        [
            _criterion(
                outcome="unknown",
                state="review_required",
                state_reason="review_required",
                category="diagnosis",
                criterion_text="Metastatic melanoma",
                evidence_payload={
                    "patient_conditions": [],
                    "snapshot_match_metadata": {
                        "logic_group_id": "33333333-3333-3333-3333-333333333333",
                        "logic_operator": "OR",
                    },
                    "snapshot_missing_data": True,
                    "member_criterion_texts": [
                        "Metastatic melanoma",
                        "Metastatic pancreatic cancer",
                    ],
                    "member_categories": ["diagnosis", "diagnosis"],
                },
            ),
            _criterion(
                outcome="unknown",
                state="structured_safe",
                state_reason=None,
                category="diagnosis",
                criterion_text="Metastatic pancreatic cancer",
                evidence_payload={
                    "patient_conditions": [],
                    "snapshot_match_metadata": {
                        "logic_group_id": "33333333-3333-3333-3333-333333333333",
                        "logic_operator": "OR",
                    },
                },
            ),
        ]
    ))

    assert report.missing_data == []
    assert len(report.review_required) == 1
    assert report.review_required[0].criterion_text == "Metastatic melanoma OR Metastatic pancreatic cancer"


def test_grouped_or_mixed_categories_use_logic_group_category():
    report = MatchGapReportResponse.model_validate(build_gap_report_payload(
        [
            _criterion(
                outcome="not_matched",
                state="structured_safe",
                category="diagnosis",
                criterion_text="Metastatic melanoma",
                evidence_payload={
                    "snapshot_match_metadata": {
                        "logic_group_id": "44444444-4444-4444-4444-444444444444",
                        "logic_operator": "OR",
                    },
                    "member_criterion_texts": ["Metastatic melanoma", "BRAF V600E mutation"],
                    "member_categories": ["diagnosis", "biomarker"],
                },
            ),
            _criterion(
                outcome="not_matched",
                state="structured_safe",
                category="biomarker",
                criterion_text="BRAF V600E mutation",
                evidence_payload={
                    "snapshot_match_metadata": {
                        "logic_group_id": "44444444-4444-4444-4444-444444444444",
                        "logic_operator": "OR",
                    },
                },
            ),
        ]
    ))

    assert len(report.hard_blockers) == 1
    assert report.hard_blockers[0].category == "logic_group"


def test_grouped_raw_items_collapse_without_order_dependence():
    report = MatchGapReportResponse.model_validate(build_gap_report_payload(
        [
            _criterion(
                outcome="requires_review",
                state="review_required",
                state_reason="review_required:fuzzy_match",
                category="diagnosis",
                criterion_text="Metastatic melanoma",
                evidence_payload={
                    "snapshot_match_metadata": {
                        "logic_group_id": "55555555-5555-5555-5555-555555555555",
                        "logic_operator": "OR",
                    }
                },
            ),
            _criterion(
                outcome="matched",
                state="structured_safe",
                category="diagnosis",
                criterion_text="Metastatic breast cancer",
                evidence_payload={
                    "snapshot_match_metadata": {
                        "logic_group_id": "55555555-5555-5555-5555-555555555555",
                        "logic_operator": "OR",
                    }
                },
            ),
        ]
    ))

    assert report.review_required == []
    assert report.hard_blockers == []
    assert report.missing_data == []
