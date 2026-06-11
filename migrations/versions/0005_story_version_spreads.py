"""Structured per-spread story text.

Adds a nullable `spreads` JSONB column to story_versions holding the 12
per-spread strings authored by the writer. Legacy rows keep NULL and the
compositor falls back to paginating `content`.

Revision ID: 0005_story_version_spreads
Revises: 0004_three_phase_review
Create Date: 2026-06-10

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0005_story_version_spreads"
down_revision: str | None = "0004_three_phase_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "story_versions",
        sa.Column("spreads", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("story_versions", "spreads")
