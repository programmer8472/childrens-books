"""Human-requested cancel.

Adds CANCELLED to the bookstatus enum and a cancel_requested flag on books.
The pipeline tasks check the flag at each stage boundary and transition the
book to CANCELLED instead of advancing.

Revision ID: 0006_cancel
Revises: 0005_story_version_spreads
Create Date: 2026-06-10

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_cancel"
down_revision: str | None = "0005_story_version_spreads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.get_bind().execute(sa.text("ALTER TYPE bookstatus ADD VALUE IF NOT EXISTS 'CANCELLED'"))
    op.add_column(
        "books",
        sa.Column("cancel_requested", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("books", "cancel_requested")
    # PostgreSQL cannot drop an enum value; CANCELLED is left in place (harmless).
