"""Add book_metadata and export_manifest columns to books table.

Revision ID: 0003_book_metadata_export
Revises: 0002_schema
Create Date: 2026-06-08

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003_book_metadata_export"
down_revision: str | None = "0002_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("books", sa.Column("book_metadata", JSONB, nullable=True))
    op.add_column("books", sa.Column("export_manifest", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("books", "export_manifest")
    op.drop_column("books", "book_metadata")
