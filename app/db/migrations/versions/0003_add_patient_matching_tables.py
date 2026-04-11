"""add patient matching tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-11 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("sex", sa.String(), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("ecog_status", sa.Integer(), nullable=True),
        sa.Column("is_healthy_volunteer", sa.Boolean(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("state", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id"),
    )

    for table_name in (
        "patient_conditions",
        "patient_biomarkers",
        "patient_labs",
        "patient_therapies",
        "patient_medications",
    ):
        extra_columns = []
        if table_name == "patient_biomarkers":
            extra_columns.append(sa.Column("value_text", sa.String(), nullable=True))
        if table_name == "patient_labs":
            extra_columns.extend(
                [
                    sa.Column("value_numeric", sa.Float(), nullable=True),
                    sa.Column("value_text", sa.String(), nullable=True),
                    sa.Column("unit", sa.String(), nullable=True),
                ]
            )
        if table_name == "patient_therapies":
            extra_columns.extend(
                [
                    sa.Column("line_of_therapy", sa.Integer(), nullable=True),
                    sa.Column("completed", sa.Boolean(), nullable=True),
                ]
            )
        if table_name == "patient_medications":
            extra_columns.append(sa.Column("active", sa.Boolean(), nullable=False))

        op.create_table(
            table_name,
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("description", sa.String(), nullable=False),
            sa.Column("coded_concepts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            *extra_columns,
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(f"ix_{table_name}_patient_id", table_name, ["patient_id"], unique=False)

    op.create_table(
        "match_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("total_trials_evaluated", sa.Integer(), nullable=False),
        sa.Column("eligible_trials", sa.Integer(), nullable=False),
        sa.Column("possible_trials", sa.Integer(), nullable=False),
        sa.Column("ineligible_trials", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_match_runs_patient_id", "match_runs", ["patient_id"], unique=False)

    op.create_table(
        "match_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trial_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("overall_status", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("favorable_count", sa.Integer(), nullable=False),
        sa.Column("unfavorable_count", sa.Integer(), nullable=False),
        sa.Column("unknown_count", sa.Integer(), nullable=False),
        sa.Column("requires_review_count", sa.Integer(), nullable=False),
        sa.Column("summary_explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["match_run_id"], ["match_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trial_id"], ["trials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_run_id", "trial_id", name="uq_match_run_trial"),
    )
    op.create_index("ix_match_results_match_run_id", "match_results", ["match_run_id"], unique=False)
    op.create_index("ix_match_results_patient_id", "match_results", ["patient_id"], unique=False)
    op.create_index("ix_match_results_trial_id", "match_results", ["trial_id"], unique=False)
    op.create_index("ix_match_results_overall_status", "match_results", ["overall_status"], unique=False)

    op.create_table(
        "match_result_criteria",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("criterion_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_label", sa.String(), nullable=False),
        sa.Column("criterion_type", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("criterion_text", sa.Text(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("explanation_text", sa.Text(), nullable=True),
        sa.Column("explanation_type", sa.String(), nullable=True),
        sa.Column("evidence_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["criterion_id"], ["extracted_criteria.id"]),
        sa.ForeignKeyConstraint(["match_result_id"], ["match_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_match_result_criteria_match_result_id", "match_result_criteria", ["match_result_id"], unique=False)
    op.create_index("ix_match_result_criteria_criterion_id", "match_result_criteria", ["criterion_id"], unique=False)
    op.create_index("ix_match_result_criteria_pipeline_run_id", "match_result_criteria", ["pipeline_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_match_result_criteria_pipeline_run_id", table_name="match_result_criteria")
    op.drop_index("ix_match_result_criteria_criterion_id", table_name="match_result_criteria")
    op.drop_index("ix_match_result_criteria_match_result_id", table_name="match_result_criteria")
    op.drop_table("match_result_criteria")
    op.drop_index("ix_match_results_overall_status", table_name="match_results")
    op.drop_index("ix_match_results_trial_id", table_name="match_results")
    op.drop_index("ix_match_results_patient_id", table_name="match_results")
    op.drop_index("ix_match_results_match_run_id", table_name="match_results")
    op.drop_table("match_results")
    op.drop_index("ix_match_runs_patient_id", table_name="match_runs")
    op.drop_table("match_runs")
    for table_name in (
        "patient_medications",
        "patient_therapies",
        "patient_labs",
        "patient_biomarkers",
        "patient_conditions",
    ):
        op.drop_index(f"ix_{table_name}_patient_id", table_name=table_name)
        op.drop_table(table_name)
    op.drop_table("patients")
