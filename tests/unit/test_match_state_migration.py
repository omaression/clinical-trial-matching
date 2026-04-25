from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import sqlalchemy as sa

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
backfill_match_result_criteria_states = _MIGRATION._backfill_match_result_criteria_states
backfill_match_result_states = _MIGRATION._backfill_match_result_states


def _create_backfill_test_connection():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                CREATE TABLE match_results (
                    id TEXT PRIMARY KEY,
                    requires_review_count INTEGER,
                    state TEXT,
                    state_reason TEXT
                )
                """
            )
        )
        connection.execute(
            sa.text(
                """
                CREATE TABLE match_result_criteria (
                    id TEXT PRIMARY KEY,
                    match_result_id TEXT,
                    criterion_id TEXT,
                    criterion_type TEXT,
                    outcome TEXT,
                    source_type TEXT,
                    evidence_payload TEXT,
                    state TEXT,
                    state_reason TEXT
                )
                """
            )
        )
    return engine


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


def test_backfill_signal_preserves_rejected_snapshot_state():
    state, reason = criterion_state_from_backfill_signal(
        outcome="unknown",
        source_type="extracted",
        review_reason=None,
        review_status="rejected",
    )

    assert state == "blocked_unsupported"
    assert reason == "rejected"


def test_backfill_signal_flags_legacy_extracted_rows_as_low_confidence_unverifiable():
    state, reason = criterion_state_from_backfill_signal(
        outcome="matched",
        source_type="extracted",
        review_reason=None,
    )

    assert state == "structured_low_confidence"
    assert reason == "legacy_state_unverifiable"


def test_backfill_signal_treats_accepted_snapshot_status_as_safe():
    state, reason = criterion_state_from_backfill_signal(
        outcome="matched",
        source_type="extracted",
        review_reason=None,
        review_status="accepted",
    )

    assert state == "structured_safe"
    assert reason is None


def test_match_state_backfill_prefers_review_required_counts():
    state, reason = match_state_from_backfilled_criteria(
        requires_review_count=1,
        has_review_required_criterion=False,
        has_blocked_unsupported_criterion=False,
        has_legacy_unverifiable_criterion=False,
    )

    assert state == "review_required"
    assert reason == "review_required"


def test_match_state_backfill_prefers_review_required_criterion_state_when_counter_is_stale():
    state, reason = match_state_from_backfilled_criteria(
        requires_review_count=0,
        has_review_required_criterion=True,
        has_blocked_unsupported_criterion=False,
        has_legacy_unverifiable_criterion=False,
    )

    assert state == "review_required"
    assert reason == "review_required"


def test_match_state_backfill_flags_blocked_unsupported_criteria():
    state, reason = match_state_from_backfilled_criteria(
        requires_review_count=0,
        has_review_required_criterion=False,
        has_blocked_unsupported_criterion=True,
        has_legacy_unverifiable_criterion=False,
    )

    assert state == "blocked_unsupported"
    assert reason == "blocked_unsupported"


def test_match_state_backfill_flags_legacy_unverifiable_criteria_as_low_confidence():
    state, reason = match_state_from_backfilled_criteria(
        requires_review_count=0,
        has_review_required_criterion=False,
        has_blocked_unsupported_criterion=False,
        has_legacy_unverifiable_criterion=True,
    )

    assert state == "structured_low_confidence"
    assert reason == "legacy_state_unverifiable"


def test_match_state_backfill_keeps_structured_only_rows_safe():
    state, reason = match_state_from_backfilled_criteria(
        requires_review_count=0,
        has_review_required_criterion=False,
        has_blocked_unsupported_criterion=False,
        has_legacy_unverifiable_criterion=False,
    )

    assert state == "structured_safe"
    assert reason is None


def test_backfill_preserves_rejected_snapshot_state_from_evidence_payload():
    engine = _create_backfill_test_connection()

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO match_results (id, requires_review_count, state, state_reason)
                VALUES ('match-1', 0, 'structured_safe', NULL)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO match_result_criteria (
                    id,
                    match_result_id,
                    criterion_id,
                    criterion_type,
                    outcome,
                    source_type,
                    evidence_payload,
                    state,
                    state_reason
                ) VALUES (
                    'mrc-1',
                    'match-1',
                    'criterion-1',
                    'inclusion',
                    'unknown',
                    'extracted',
                    '{"review_status": "rejected"}',
                    'structured_safe',
                    NULL
                )
                """
            )
        )

        backfill_match_result_criteria_states(connection)
        backfill_match_result_states(connection)

        criterion_row = connection.execute(
            sa.text("SELECT state, state_reason FROM match_result_criteria WHERE id = 'mrc-1'")
        ).mappings().one()
        match_row = connection.execute(
            sa.text("SELECT state, state_reason FROM match_results WHERE id = 'match-1'")
        ).mappings().one()

    assert criterion_row["state"] == "blocked_unsupported"
    assert criterion_row["state_reason"] == "rejected"
    assert match_row["state"] == "blocked_unsupported"
    assert match_row["state_reason"] == "blocked_unsupported"


def test_backfill_uses_review_required_criterion_state_even_when_match_counter_is_zero():
    engine = _create_backfill_test_connection()

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO match_results (id, requires_review_count, state, state_reason)
                VALUES ('match-review', 0, 'structured_safe', NULL)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO match_result_criteria (
                    id,
                    match_result_id,
                    criterion_id,
                    criterion_type,
                    outcome,
                    source_type,
                    evidence_payload,
                    state,
                    state_reason
                ) VALUES (
                    'mrc-review',
                    'match-review',
                    'criterion-review',
                    'inclusion',
                    'requires_review',
                    'extracted',
                    '{"review_reason": "fuzzy_match", "review_status": "pending"}',
                    'structured_safe',
                    NULL
                )
                """
            )
        )

        backfill_match_result_criteria_states(connection)
        backfill_match_result_states(connection)

        match_row = connection.execute(
            sa.text("SELECT state, state_reason FROM match_results WHERE id = 'match-review'")
        ).mappings().one()

    assert match_row["state"] == "review_required"
    assert match_row["state_reason"] == "review_required"


def test_backfill_falls_back_to_legacy_low_confidence_when_source_criterion_missing():
    engine = _create_backfill_test_connection()

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO match_results (id, requires_review_count, state, state_reason)
                VALUES ('match-2', 0, 'structured_safe', NULL)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO match_result_criteria (
                    id,
                    match_result_id,
                    criterion_id,
                    criterion_type,
                    outcome,
                    source_type,
                    evidence_payload,
                    state,
                    state_reason
                ) VALUES (
                    'mrc-2',
                    'match-2',
                    'missing-criterion',
                    'inclusion',
                    'matched',
                    'extracted',
                    NULL,
                    'structured_safe',
                    NULL
                )
                """
            )
        )

        backfill_match_result_criteria_states(connection)
        backfill_match_result_states(connection)

        criterion_row = connection.execute(
            sa.text("SELECT state, state_reason FROM match_result_criteria WHERE id = 'mrc-2'")
        ).mappings().one()
        match_row = connection.execute(
            sa.text("SELECT state, state_reason FROM match_results WHERE id = 'match-2'")
        ).mappings().one()

    assert criterion_row["state"] == "structured_low_confidence"
    assert criterion_row["state_reason"] == "legacy_state_unverifiable"
    assert match_row["state"] == "structured_low_confidence"
    assert match_row["state_reason"] == "legacy_state_unverifiable"
