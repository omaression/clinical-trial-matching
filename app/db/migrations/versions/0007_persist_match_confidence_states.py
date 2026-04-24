"""persist match confidence states

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-24 00:00:00.000000

"""

from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UNSPECIFIED_REVIEW_REASON = "unspecified_review_reason"
UNVERIFIABLE_LEGACY_REASON = "legacy_state_unverifiable"


def _review_reason_from_evidence(evidence_payload: Any) -> str | None:
    if isinstance(evidence_payload, dict):
        review_reason = evidence_payload.get("review_reason")
        if isinstance(review_reason, str) and review_reason:
            return review_reason
    return None


def _criterion_state_from_backfill_signal(
    *,
    outcome: str,
    source_type: str,
    review_reason: str | None,
) -> tuple[str, str | None]:
    if outcome == "requires_review":
        return "review_required", f"review_required:{review_reason or UNSPECIFIED_REVIEW_REASON}"
    if source_type == "structured":
        return "structured_safe", None
    return "blocked_unsupported", UNVERIFIABLE_LEGACY_REASON


def _match_state_from_backfilled_criteria(
    *,
    requires_review_count: int | None,
    has_legacy_unverifiable_criterion: bool,
) -> tuple[str, str | None]:
    if (requires_review_count or 0) > 0:
        return "review_required", "review_required"
    if has_legacy_unverifiable_criterion:
        return "blocked_unsupported", UNVERIFIABLE_LEGACY_REASON
    return "structured_safe", None


def _backfill_match_result_criteria_states(connection) -> None:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                id,
                outcome,
                source_type,
                evidence_payload
            FROM match_result_criteria
            """
        )
    ).mappings()

    updates = []
    for row in rows:
        state, state_reason = _criterion_state_from_backfill_signal(
            outcome=row["outcome"],
            source_type=row["source_type"],
            review_reason=_review_reason_from_evidence(row["evidence_payload"]),
        )
        updates.append({"id": row["id"], "state": state, "state_reason": state_reason})

    if updates:
        connection.execute(
            sa.text(
                """
                UPDATE match_result_criteria
                SET state = :state, state_reason = :state_reason
                WHERE id = :id
                """
            ),
            updates,
        )


def _backfill_match_result_states(connection) -> None:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                mr.id,
                mr.requires_review_count,
                EXISTS (
                    SELECT 1
                    FROM match_result_criteria AS mrc
                    WHERE mrc.match_result_id = mr.id
                      AND mrc.state = 'blocked_unsupported'
                      AND mrc.state_reason = 'legacy_state_unverifiable'
                ) AS has_legacy_unverifiable_criterion
            FROM match_results AS mr
            """
        )
    ).mappings()

    updates = []
    for row in rows:
        state, state_reason = _match_state_from_backfilled_criteria(
            requires_review_count=row["requires_review_count"],
            has_legacy_unverifiable_criterion=row["has_legacy_unverifiable_criterion"],
        )
        updates.append({"id": row["id"], "state": state, "state_reason": state_reason})

    if updates:
        connection.execute(
            sa.text(
                """
                UPDATE match_results
                SET state = :state, state_reason = :state_reason
                WHERE id = :id
                """
            ),
            updates,
        )


def upgrade() -> None:
    op.add_column(
        "match_results",
        sa.Column("state", sa.String(), nullable=False, server_default="structured_safe"),
    )
    op.add_column("match_results", sa.Column("state_reason", sa.String(), nullable=True))
    op.add_column(
        "match_result_criteria",
        sa.Column("state", sa.String(), nullable=False, server_default="structured_safe"),
    )
    op.add_column("match_result_criteria", sa.Column("state_reason", sa.String(), nullable=True))

    connection = op.get_bind()
    _backfill_match_result_criteria_states(connection)
    _backfill_match_result_states(connection)

    op.alter_column("match_results", "state", server_default=None)
    op.alter_column("match_result_criteria", "state", server_default=None)


def downgrade() -> None:
    op.drop_column("match_result_criteria", "state_reason")
    op.drop_column("match_result_criteria", "state")
    op.drop_column("match_results", "state_reason")
    op.drop_column("match_results", "state")
