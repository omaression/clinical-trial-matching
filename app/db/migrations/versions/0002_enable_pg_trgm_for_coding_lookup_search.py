"""enable pg_trgm for coding lookup fuzzy search

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-11 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_coding_lookups_display_trgm
        ON coding_lookups
        USING gin (display gin_trgm_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_coding_lookups_synonyms_text_trgm
        ON coding_lookups
        USING gin ((array_to_string(COALESCE(synonyms, ARRAY[]::text[]), ' ')) gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_coding_lookups_synonyms_text_trgm")
    op.execute("DROP INDEX IF EXISTS ix_coding_lookups_display_trgm")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
