"""persist match confidence states

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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

    op.execute(
        """
        UPDATE match_result_criteria
        SET
            state = CASE
                WHEN outcome = 'requires_review' THEN 'review_required'
                ELSE 'structured_safe'
            END,
            state_reason = CASE
                WHEN outcome = 'requires_review' THEN 'review_required:unspecified_review_reason'
                ELSE NULL
            END
        """
    )
    op.execute(
        """
        UPDATE match_results AS mr
        SET
            state = CASE
                WHEN EXISTS (
                    SELECT 1 FROM match_result_criteria mrc
                    WHERE mrc.match_result_id = mr.id AND mrc.state = 'review_required'
                ) THEN 'review_required'
                WHEN EXISTS (
                    SELECT 1 FROM match_result_criteria mrc
                    WHERE mrc.match_result_id = mr.id AND mrc.state = 'blocked_unsupported'
                ) THEN 'blocked_unsupported'
                WHEN EXISTS (
                    SELECT 1 FROM match_result_criteria mrc
                    WHERE mrc.match_result_id = mr.id AND mrc.state = 'structured_low_confidence'
                ) THEN 'structured_low_confidence'
                ELSE 'structured_safe'
            END,
            state_reason = CASE
                WHEN EXISTS (
                    SELECT 1 FROM match_result_criteria mrc
                    WHERE mrc.match_result_id = mr.id AND mrc.state = 'review_required'
                ) THEN 'review_required'
                WHEN EXISTS (
                    SELECT 1 FROM match_result_criteria mrc
                    WHERE mrc.match_result_id = mr.id AND mrc.state = 'blocked_unsupported'
                ) THEN 'blocked_unsupported'
                WHEN EXISTS (
                    SELECT 1 FROM match_result_criteria mrc
                    WHERE mrc.match_result_id = mr.id AND mrc.state = 'structured_low_confidence'
                ) THEN 'low_confidence'
                ELSE NULL
            END
        """
    )

    op.alter_column("match_results", "state", server_default=None)
    op.alter_column("match_result_criteria", "state", server_default=None)


def downgrade() -> None:
    op.drop_column("match_result_criteria", "state_reason")
    op.drop_column("match_result_criteria", "state")
    op.drop_column("match_results", "state_reason")
    op.drop_column("match_results", "state")
