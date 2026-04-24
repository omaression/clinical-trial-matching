from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "db"
    / "migrations"
    / "versions"
    / "0007_persist_match_confidence_states.py"
)
_SPEC = spec_from_file_location("migration_0007", _MIGRATION_PATH)
assert _SPEC and _SPEC.loader
_MIGRATION = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MIGRATION)

criterion_state_from_backfill_signal = _MIGRATION._criterion_state_from_backfill_signal
match_state_from_backfilled_criteria = _MIGRATION._match_state_from_backfilled_criteria
review_reason_from_evidence = _MIGRATION._review_reason_from_evidence


def test_review_reason_from_evidence_reads_snapshot_reason():
    assert review_reason_from_evidence({"review_reason": "fuzzy_match"}) == "fuzzy_match"


def test_backfill_signal_marks_requires_review_rows_with_snapshot_reason():
    state, reason = criterion_state_from_backfill_signal(
        outcome="requires_review",
        source_type="extracted",
        review_reason="fuzzy_match",
    )

    assert state == "review_required"
    assert reason == "review_required:fuzzy_match"


def test_backfill_signal_keeps_structured_rows_safe():
    state, reason = criterion_state_from_backfill_signal(
        outcome="matched",
        source_type="structured",
        review_reason=None,
    )

    assert state == "structured_safe"
    assert reason is None


def test_backfill_signal_flags_legacy_extracted_rows_as_unverifiable():
    state, reason = criterion_state_from_backfill_signal(
        outcome="matched",
        source_type="extracted",
        review_reason=None,
    )

    assert state == "blocked_unsupported"
    assert reason == "legacy_state_unverifiable"


def test_match_state_backfill_prefers_review_required_counts():
    state, reason = match_state_from_backfilled_criteria(
        requires_review_count=1,
        has_legacy_unverifiable_criterion=False,
    )

    assert state == "review_required"
    assert reason == "review_required"


def test_match_state_backfill_flags_legacy_unverifiable_criteria():
    state, reason = match_state_from_backfilled_criteria(
        requires_review_count=0,
        has_legacy_unverifiable_criterion=True,
    )

    assert state == "blocked_unsupported"
    assert reason == "legacy_state_unverifiable"


def test_match_state_backfill_keeps_structured_only_rows_safe():
    state, reason = match_state_from_backfilled_criteria(
        requires_review_count=0,
        has_legacy_unverifiable_criterion=False,
    )

    assert state == "structured_safe"
    assert reason is None
