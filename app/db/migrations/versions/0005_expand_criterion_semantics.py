"""expand extracted criterion semantics

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-12 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("extracted_criteria", sa.Column("source_sentence", sa.Text(), nullable=True))
    op.add_column("extracted_criteria", sa.Column("source_clause_text", sa.Text(), nullable=True))
    op.add_column("extracted_criteria", sa.Column("primary_semantic_category", sa.String(), nullable=True))
    op.add_column(
        "extracted_criteria",
        sa.Column("secondary_semantic_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("extracted_criteria", sa.Column("specimen_type", sa.String(), nullable=True))
    op.add_column("extracted_criteria", sa.Column("testing_modality", sa.String(), nullable=True))
    op.add_column("extracted_criteria", sa.Column("disease_subtype", sa.String(), nullable=True))
    op.add_column("extracted_criteria", sa.Column("histology_text", sa.String(), nullable=True))
    op.add_column(
        "extracted_criteria",
        sa.Column("assay_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "extracted_criteria",
        sa.Column("confidence_factors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.execute("UPDATE extracted_criteria SET source_clause_text = original_text WHERE source_clause_text IS NULL")
    op.execute("UPDATE extracted_criteria SET primary_semantic_category = category WHERE primary_semantic_category IS NULL")
    op.execute(
        "UPDATE extracted_criteria SET secondary_semantic_tags = '[]'::jsonb WHERE secondary_semantic_tags IS NULL"
    )
    op.execute(
        "UPDATE extracted_criteria SET confidence_factors = jsonb_build_object('migrated', true) "
        "WHERE confidence_factors IS NULL"
    )


def downgrade() -> None:
    op.drop_column("extracted_criteria", "confidence_factors")
    op.drop_column("extracted_criteria", "assay_context")
    op.drop_column("extracted_criteria", "histology_text")
    op.drop_column("extracted_criteria", "disease_subtype")
    op.drop_column("extracted_criteria", "testing_modality")
    op.drop_column("extracted_criteria", "specimen_type")
    op.drop_column("extracted_criteria", "secondary_semantic_tags")
    op.drop_column("extracted_criteria", "primary_semantic_category")
    op.drop_column("extracted_criteria", "source_clause_text")
    op.drop_column("extracted_criteria", "source_sentence")
