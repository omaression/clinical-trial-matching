"""initial schema with all 6 tables

Revision ID: 0001
Revises:
Create Date: 2026-04-09 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- trials ---
    op.create_table(
        "trials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nct_id", sa.String(), nullable=False),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("brief_title", sa.String(), nullable=False),
        sa.Column("official_title", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("phase", sa.String(), nullable=True),
        sa.Column("conditions", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("interventions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("eligibility_text", sa.Text(), nullable=True),
        sa.Column("eligible_min_age", sa.String(), nullable=True),
        sa.Column("eligible_max_age", sa.String(), nullable=True),
        sa.Column("eligible_sex", sa.String(), nullable=True),
        sa.Column("accepts_healthy", sa.Boolean(), nullable=True),
        sa.Column("structured_eligibility", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sponsor", sa.String(), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extraction_status", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nct_id"),
    )
    op.create_index(op.f("ix_trials_content_hash"), "trials", ["content_hash"], unique=False)
    op.create_index(op.f("ix_trials_nct_id"), "trials", ["nct_id"], unique=False)
    op.create_index(op.f("ix_trials_phase"), "trials", ["phase"], unique=False)
    op.create_index(op.f("ix_trials_status"), "trials", ["status"], unique=False)
    op.create_index(
        "ix_trials_conditions", "trials", ["conditions"], unique=False, postgresql_using="gin"
    )

    # --- trial_sites ---
    op.create_table(
        "trial_sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trial_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facility", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("state", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("zip", sa.String(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["trial_id"], ["trials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trial_sites_trial_id"), "trial_sites", ["trial_id"], unique=False)
    op.create_index("ix_trial_sites_geo", "trial_sites", ["country", "state", "city"], unique=False)

    # --- pipeline_runs ---
    op.create_table(
        "pipeline_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trial_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pipeline_version", sa.String(), nullable=False),
        sa.Column("input_hash", sa.String(), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("criteria_extracted_count", sa.Integer(), nullable=True),
        sa.Column("review_required_count", sa.Integer(), nullable=True),
        sa.Column("diff_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["trial_id"], ["trials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pipeline_runs_trial_id"), "pipeline_runs", ["trial_id"], unique=False)
    op.create_index(
        op.f("ix_pipeline_runs_pipeline_version"), "pipeline_runs", ["pipeline_version"], unique=False
    )

    # --- fhir_research_studies ---
    op.create_table(
        "fhir_research_studies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trial_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["trial_id"], ["trials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- extracted_criteria ---
    op.create_table(
        "extracted_criteria",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trial_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("parse_status", sa.String(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("operator", sa.String(), nullable=True),
        sa.Column("value_low", sa.Float(), nullable=True),
        sa.Column("value_high", sa.Float(), nullable=True),
        sa.Column("value_text", sa.String(), nullable=True),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("raw_expression", sa.String(), nullable=True),
        sa.Column("negated", sa.Boolean(), nullable=False),
        sa.Column("timeframe_operator", sa.String(), nullable=True),
        sa.Column("timeframe_value", sa.Float(), nullable=True),
        sa.Column("timeframe_unit", sa.String(), nullable=True),
        sa.Column("logic_group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("logic_operator", sa.String(), nullable=False),
        sa.Column("coded_concepts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("review_required", sa.Boolean(), nullable=False),
        sa.Column("review_reason", sa.String(), nullable=True),
        sa.Column("review_status", sa.String(), nullable=True),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("original_extracted", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pipeline_version", sa.String(), nullable=False),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["trial_id"], ["trials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_extracted_criteria_trial_id"), "extracted_criteria", ["trial_id"], unique=False
    )
    op.create_index(
        op.f("ix_extracted_criteria_category"), "extracted_criteria", ["category"], unique=False
    )
    op.create_index(
        op.f("ix_extracted_criteria_pipeline_run_id"),
        "extracted_criteria",
        ["pipeline_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_criteria_review",
        "extracted_criteria",
        ["review_required"],
        unique=False,
        postgresql_where=sa.text("review_required = true"),
    )
    op.create_index(
        "ix_criteria_coded",
        "extracted_criteria",
        ["coded_concepts"],
        unique=False,
        postgresql_using="gin",
    )

    # --- coding_lookups ---
    op.create_table(
        "coding_lookups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("system", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("display", sa.String(), nullable=False),
        sa.Column("synonyms", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("parent_codes", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("system", "code", name="uq_coding_system_code"),
    )
    op.create_index(
        "ix_coding_synonyms", "coding_lookups", ["synonyms"], unique=False, postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_index("ix_coding_synonyms", table_name="coding_lookups", postgresql_using="gin")
    op.drop_table("coding_lookups")
    op.drop_index("ix_criteria_coded", table_name="extracted_criteria", postgresql_using="gin")
    op.drop_index("ix_criteria_review", table_name="extracted_criteria")
    op.drop_index(op.f("ix_extracted_criteria_pipeline_run_id"), table_name="extracted_criteria")
    op.drop_index(op.f("ix_extracted_criteria_category"), table_name="extracted_criteria")
    op.drop_index(op.f("ix_extracted_criteria_trial_id"), table_name="extracted_criteria")
    op.drop_table("extracted_criteria")
    op.drop_table("fhir_research_studies")
    op.drop_index(op.f("ix_pipeline_runs_pipeline_version"), table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_trial_id"), table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
    op.drop_index("ix_trial_sites_geo", table_name="trial_sites")
    op.drop_index(op.f("ix_trial_sites_trial_id"), table_name="trial_sites")
    op.drop_table("trial_sites")
    op.drop_index("ix_trials_conditions", table_name="trials", postgresql_using="gin")
    op.drop_index(op.f("ix_trials_status"), table_name="trials")
    op.drop_index(op.f("ix_trials_phase"), table_name="trials")
    op.drop_index(op.f("ix_trials_nct_id"), table_name="trials")
    op.drop_index(op.f("ix_trials_content_hash"), table_name="trials")
    op.drop_table("trials")
