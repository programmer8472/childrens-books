"""All Unit 1 tables: books, story_versions, judgements, images, character_assets, audit_log.

Revision ID: 0002_schema
Revises: 0001_baseline
Create Date: 2026-06-07

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0002_schema"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_bookstatus = sa.Enum(
    "DRAFT_BRIEF", "OUTLINING", "WRITING", "JUDGING", "REVISION",
    "AWAITING_APPROVAL", "APPROVED", "GENERATING_IMAGES", "GENERATING_COVER",
    "DRAFTING_METADATA", "EXPORTING", "EXPORT_READY", "DONE", "RETIRED",
    name="bookstatus",
)


def upgrade() -> None:
    _bookstatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "books",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("brief", JSONB, nullable=False),
        sa.Column("status", sa.Enum(name="bookstatus", create_type=False), nullable=False),
        sa.Column("max_rounds", sa.Integer, nullable=False, server_default="5"),
        sa.Column("current_round", sa.Integer, nullable=False, server_default="0"),
        sa.Column("score_threshold", sa.Float, nullable=False, server_default="7.5"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "character_assets",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("book_id", sa.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_character_assets_book_id", "character_assets", ["book_id"])

    op.create_table(
        "story_versions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("book_id", sa.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("round", sa.Integer, nullable=False),
        sa.Column("method", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("prior_critique", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_story_versions_book_id", "story_versions", ["book_id"])

    op.create_table(
        "judgements",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("book_id", sa.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("story_version_id", sa.UUID(as_uuid=True), sa.ForeignKey("story_versions.id"), nullable=False),
        sa.Column("round", sa.Integer, nullable=False),
        sa.Column("judge_prompt_version", sa.Text, nullable=False),
        sa.Column("emotional_authenticity", sa.Float, nullable=False),
        sa.Column("representation_quality", sa.Float, nullable=False),
        sa.Column("pacing", sa.Float, nullable=False),
        sa.Column("age_fit", sa.Float, nullable=False),
        sa.Column("uniqueness", sa.Float, nullable=False),
        sa.Column("weighted_total", sa.Float, nullable=False),
        sa.Column("passed", sa.Boolean, nullable=False),
        sa.Column("critique", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_judgements_book_id", "judgements", ["book_id"])
    op.create_index("ix_judgements_story_version_id", "judgements", ["story_version_id"])

    op.create_table(
        "images",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("book_id", sa.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("story_version_id", sa.UUID(as_uuid=True), sa.ForeignKey("story_versions.id"), nullable=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("scene_index", sa.Integer, nullable=True),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("provider_params", JSONB, nullable=False),
        sa.Column("seed", sa.Text, nullable=True),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_images_book_id", "images", ["book_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("book_id", sa.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("from_status", sa.Enum(name="bookstatus", create_type=False), nullable=True),
        sa.Column("to_status", sa.Enum(name="bookstatus", create_type=False), nullable=False),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_audit_log_book_id", "audit_log", ["book_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("images")
    op.drop_table("judgements")
    op.drop_table("story_versions")
    op.drop_table("character_assets")
    op.drop_table("books")
    _bookstatus.drop(op.get_bind(), checkfirst=True)
