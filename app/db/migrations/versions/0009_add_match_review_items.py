"""add match review items

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-29 00:00:00.000000

"""

import hashlib
import json
import uuid
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FOLLOW_UP_BUCKETS = ("review_required", "missing_data", "clarifiable_blockers", "unsupported")


def _string_value(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _item_key(*, bucket: str, ordinal: int, category: str, criterion_text: str, reason_code: str) -> str:
    digest_source = "\0".join([category, criterion_text, reason_code])
    digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:12]
    return f"{bucket}:{ordinal}:{digest}"


def _review_item_rows(row) -> list[dict[str, Any]]:
    payload = row["gap_report_payload"] if isinstance(row["gap_report_payload"], dict) else None
    rows: list[dict[str, Any]] = []
    if payload is not None:
        for bucket in FOLLOW_UP_BUCKETS:
            entries = payload.get(bucket, [])
            if not isinstance(entries, list):
                continue
            for ordinal, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                category = _string_value(entry.get("category")) or "logic_group"
                criterion_text = _string_value(entry.get("criterion_text")) or ""
                reason_code = (
                    _string_value(entry.get("state_reason"))
                    or _string_value(entry.get("kind"))
                    or bucket
                )
                rows.append(
                    {
                        "id": uuid.uuid4(),
                        "match_result_id": row["id"],
                        "match_run_id": row["match_run_id"],
                        "patient_id": row["patient_id"],
                        "trial_id": row["trial_id"],
                        "item_key": _item_key(
                            bucket=bucket,
                            ordinal=ordinal,
                            category=category,
                            criterion_text=criterion_text,
                            reason_code=reason_code,
                        ),
                        "bucket": bucket,
                        "reason_code": reason_code,
                        "category": category,
                        "criterion_text": criterion_text,
                        "outcome": _string_value(entry.get("outcome")),
                        "state": _string_value(entry.get("state")) or "review_required",
                        "state_reason": _string_value(entry.get("state_reason")),
                        "source_snippet": _string_value(entry.get("source_snippet")),
                        "evidence_payload": (
                            json.dumps(entry.get("evidence_payload"))
                            if isinstance(entry.get("evidence_payload"), dict)
                            else None
                        ),
                        "summary": _string_value(entry.get("summary")),
                        "created_at": row["created_at"],
                    }
                )
    if rows:
        return rows

    state = _string_value(row["state"]) or "review_required"
    unresolved = (
        (row["unknown_count"] or 0) > 0
        or (row["requires_review_count"] or 0) > 0
        or state not in {"structured_safe", "blocked_unsupported"}
        or state == "blocked_unsupported"
    )
    if not unresolved:
        return []

    bucket = "unsupported" if state == "blocked_unsupported" else "review_required"
    reason_code = _string_value(row["state_reason"]) or "legacy_state_unverifiable"
    criterion_text = "Gap report was not snapshotted for this historical match result."
    return [
        {
            "id": uuid.uuid4(),
            "match_result_id": row["id"],
            "match_run_id": row["match_run_id"],
            "patient_id": row["patient_id"],
            "trial_id": row["trial_id"],
            "item_key": _item_key(
                bucket=bucket,
                ordinal=0,
                category="historical_snapshot",
                criterion_text=criterion_text,
                reason_code=reason_code,
            ),
            "bucket": bucket,
            "reason_code": reason_code,
            "category": "historical_snapshot",
            "criterion_text": criterion_text,
            "outcome": "unknown",
            "state": state,
            "state_reason": reason_code,
            "source_snippet": None,
            "evidence_payload": None,
            "summary": row["summary_explanation"],
            "created_at": row["created_at"],
        }
    ]


def upgrade() -> None:
    op.create_table(
        "match_review_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trial_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_key", sa.String(), nullable=False),
        sa.Column("bucket", sa.String(), nullable=False),
        sa.Column("reason_code", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("criterion_text", sa.Text(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("state_reason", sa.String(), nullable=True),
        sa.Column("source_snippet", sa.Text(), nullable=True),
        sa.Column("evidence_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["match_result_id"], ["match_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["match_run_id"], ["match_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trial_id"], ["trials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_result_id", "item_key", name="uq_match_review_item_result_key"),
    )
    op.create_index("ix_match_review_items_match_result_id", "match_review_items", ["match_result_id"])
    op.create_index("ix_match_review_items_match_run_id", "match_review_items", ["match_run_id"])
    op.create_index("ix_match_review_items_patient_id", "match_review_items", ["patient_id"])
    op.create_index("ix_match_review_items_trial_id", "match_review_items", ["trial_id"])
    op.create_index("ix_match_review_items_bucket", "match_review_items", ["bucket"])
    op.create_index("ix_match_review_items_reason_code", "match_review_items", ["reason_code"])
    op.create_index("ix_match_review_items_queue", "match_review_items", ["bucket", "reason_code", "created_at"])

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT
                id,
                match_run_id,
                patient_id,
                trial_id,
                overall_status,
                unknown_count,
                requires_review_count,
                state,
                state_reason,
                summary_explanation,
                gap_report_payload,
                created_at
            FROM match_results
            """
        )
    ).mappings()

    backfill_rows = []
    for row in rows:
        backfill_rows.extend(_review_item_rows(row))

    if backfill_rows:
        connection.execute(
            sa.text(
                """
                INSERT INTO match_review_items (
                    id,
                    match_result_id,
                    match_run_id,
                    patient_id,
                    trial_id,
                    item_key,
                    bucket,
                    reason_code,
                    category,
                    criterion_text,
                    outcome,
                    state,
                    state_reason,
                    source_snippet,
                    evidence_payload,
                    summary,
                    created_at
                ) VALUES (
                    :id,
                    :match_result_id,
                    :match_run_id,
                    :patient_id,
                    :trial_id,
                    :item_key,
                    :bucket,
                    :reason_code,
                    :category,
                    :criterion_text,
                    :outcome,
                    :state,
                    :state_reason,
                    :source_snippet,
                    CAST(:evidence_payload AS JSONB),
                    :summary,
                    :created_at
                )
                """
            ),
            backfill_rows,
        )


def downgrade() -> None:
    op.drop_table("match_review_items")
