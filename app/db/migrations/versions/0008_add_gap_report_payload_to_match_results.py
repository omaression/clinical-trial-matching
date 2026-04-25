"""add gap report payload to match results

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-25 00:00:00.000000

"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfilled_gap_report(row) -> dict[str, list[dict[str, object | None]]]:
    base_entry = {
        "label": "Historical Snapshot",
        "category": "historical_snapshot",
        "criterion_text": "Gap report was not snapshotted for this historical match result.",
        "state": row["state"],
        "state_reason": row["state_reason"] or "legacy_state_unverifiable",
        "summary": row["summary_explanation"],
        "source_snippet": None,
        "evidence_payload": None,
    }
    report = {
        "hard_blockers": [],
        "clarifiable_blockers": [],
        "missing_data": [],
        "review_required": [],
        "unsupported": [],
    }
    if row["state"] == "blocked_unsupported":
        report["unsupported"].append({**base_entry, "kind": "unsupported", "outcome": "unknown"})
    if (
        row["overall_status"] == "ineligible"
        and (row["unfavorable_count"] or 0) > 0
        and row["state"] == "structured_safe"
    ):
        report["hard_blockers"].append({**base_entry, "kind": "hard_blocker", "outcome": "not_matched"})
    if (
        (row["unknown_count"] or 0) > 0
        or (row["requires_review_count"] or 0) > 0
        or (row["state"] not in {"structured_safe", "blocked_unsupported"})
    ):
        report["review_required"].append({**base_entry, "kind": "review_required", "outcome": "unknown"})
    return report


def upgrade() -> None:
    op.add_column(
        "match_results",
        sa.Column("gap_report_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT
                id,
                overall_status,
                unfavorable_count,
                unknown_count,
                requires_review_count,
                state,
                state_reason,
                summary_explanation
            FROM match_results
            """
        )
    ).mappings()

    updates = []
    for row in rows:
        updates.append({"id": row["id"], "gap_report_payload": json.dumps(_backfilled_gap_report(row))})

    if updates:
        connection.execute(
            sa.text(
                """
                UPDATE match_results
                SET gap_report_payload = CAST(:gap_report_payload AS JSONB)
                WHERE id = :id
                """
            ),
            updates,
        )


def downgrade() -> None:
    op.drop_column("match_results", "gap_report_payload")
