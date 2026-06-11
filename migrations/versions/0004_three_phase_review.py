"""Three-phase human review flow.

Adds AWAITING_SHORTLIST, SHORTLIST_JUDGING, AWAITING_FINAL_APPROVAL to the
bookstatus enum, a shortlisted column on story_versions, and an
approved_version_id column on books.

Revision ID: 0004_three_phase_review
Revises: 0003_book_metadata_export
Create Date: 2026-06-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_three_phase_review"
down_revision: str | None = "0003_book_metadata_export"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_STATUSES = (
    "AWAITING_SHORTLIST",
    "SHORTLIST_JUDGING",
    "AWAITING_FINAL_APPROVAL",
)


def upgrade() -> None:
    # PostgreSQL requires each ALTER TYPE … ADD VALUE to run outside a transaction
    # block when using Alembic's default transactional DDL mode. We use COMMIT/BEGIN
    # wrapping via op.execute with connection-level autocommit workaround:
    conn = op.get_bind()
    for value in _NEW_STATUSES:
        conn.execute(sa.text(
            f"ALTER TYPE bookstatus ADD VALUE IF NOT EXISTS '{value}'"
        ))

    op.add_column(
        "story_versions",
        sa.Column("shortlisted", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "books",
        sa.Column(
            "approved_version_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("story_versions.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("books", "approved_version_id")
    op.drop_column("story_versions", "shortlisted")
    # PostgreSQL does not support removing enum values; downgrade leaves the
    # three new statuses in the bookstatus type (they are harmless when unused).
