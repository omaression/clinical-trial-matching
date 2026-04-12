"""add patient matching flags

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-11 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("can_consent", sa.Boolean(), nullable=True))
    op.add_column("patients", sa.Column("protocol_compliant", sa.Boolean(), nullable=True))
    op.add_column("patients", sa.Column("claustrophobic", sa.Boolean(), nullable=True))
    op.add_column("patients", sa.Column("motion_intolerant", sa.Boolean(), nullable=True))
    op.add_column("patients", sa.Column("pregnant", sa.Boolean(), nullable=True))
    op.add_column("patients", sa.Column("mr_device_present", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("patients", "mr_device_present")
    op.drop_column("patients", "pregnant")
    op.drop_column("patients", "motion_intolerant")
    op.drop_column("patients", "claustrophobic")
    op.drop_column("patients", "protocol_compliant")
    op.drop_column("patients", "can_consent")
