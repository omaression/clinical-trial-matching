"""add medication exception semantics

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-13 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "extracted_criteria",
        sa.Column("exception_logic", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "extracted_criteria",
        sa.Column("exception_entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("extracted_criteria", sa.Column("allowance_text", sa.Text(), nullable=True))

    op.execute(
        "UPDATE extracted_criteria SET exception_entities = '[]'::jsonb WHERE exception_entities IS NULL"
    )


def downgrade() -> None:
    op.drop_column("extracted_criteria", "allowance_text")
    op.drop_column("extracted_criteria", "exception_entities")
    op.drop_column("extracted_criteria", "exception_logic")
