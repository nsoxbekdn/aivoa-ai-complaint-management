"""add internal QA analysis and intake transcript fields

Revision ID: a42c7b7d91ef
Revises: f66f403cf40a
Create Date: 2026-07-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a42c7b7d91ef"
down_revision: Union[str, None] = "f66f403cf40a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON_FIELD = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("complaints") as batch_op:
        batch_op.add_column(sa.Column("risk_confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("patient_safety_concern", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("product_quality_concern", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("initial_investigation_steps", JSON_FIELD, nullable=True))
        batch_op.add_column(sa.Column("duplicate_candidates", JSON_FIELD, nullable=True))
        batch_op.add_column(sa.Column("intake_transcript", JSON_FIELD, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("complaints") as batch_op:
        batch_op.drop_column("intake_transcript")
        batch_op.drop_column("duplicate_candidates")
        batch_op.drop_column("initial_investigation_steps")
        batch_op.drop_column("product_quality_concern")
        batch_op.drop_column("patient_safety_concern")
        batch_op.drop_column("risk_confidence")
