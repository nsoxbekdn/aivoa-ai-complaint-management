"""add OCR provenance and analysis warnings

Revision ID: b0d2d1e487a9
Revises: a42c7b7d91ef
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b0d2d1e487a9"
down_revision: str | None = "a42c7b7d91ef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "complaints",
        sa.Column(
            "analysis_warnings",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )
    op.add_column(
        "complaints",
        sa.Column(
            "source_documents",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("complaints", "source_documents")
    op.drop_column("complaints", "analysis_warnings")
