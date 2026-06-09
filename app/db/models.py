"""SQLAlchemy ORM models for all Unit 1 tables."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.enums import BookStatus
from app.db.session import Base

_bookstatus_col = sa.Enum(BookStatus, name="bookstatus", create_type=False)


class Book(Base):
    __tablename__ = "books"

    id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    brief: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[BookStatus] = mapped_column(_bookstatus_col, nullable=False, default=BookStatus.DRAFT_BRIEF)
    max_rounds: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=5)
    current_round: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    score_threshold: Mapped[float] = mapped_column(sa.Float, nullable=False, default=7.5)
    book_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    export_manifest: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)

    story_versions: Mapped[list["StoryVersion"]] = relationship(back_populates="book", order_by="StoryVersion.created_at")
    character_assets: Mapped[list["CharacterAsset"]] = relationship(back_populates="book")
    audit_log: Mapped[list["AuditLog"]] = relationship(back_populates="book", order_by="AuditLog.created_at")


class StoryVersion(Base):
    __tablename__ = "story_versions"

    id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=False, index=True)
    round: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    method: Mapped[str] = mapped_column(sa.Text, nullable=False)
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    prior_critique: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)

    book: Mapped["Book"] = relationship(back_populates="story_versions")
    judgements: Mapped[list["Judgement"]] = relationship(back_populates="story_version")


class Judgement(Base):
    __tablename__ = "judgements"

    id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=False, index=True)
    story_version_id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), sa.ForeignKey("story_versions.id"), nullable=False, index=True)
    round: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    judge_prompt_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    emotional_authenticity: Mapped[float] = mapped_column(sa.Float, nullable=False)
    representation_quality: Mapped[float] = mapped_column(sa.Float, nullable=False)
    pacing: Mapped[float] = mapped_column(sa.Float, nullable=False)
    age_fit: Mapped[float] = mapped_column(sa.Float, nullable=False)
    uniqueness: Mapped[float] = mapped_column(sa.Float, nullable=False)
    weighted_total: Mapped[float] = mapped_column(sa.Float, nullable=False)
    passed: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    critique: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)

    story_version: Mapped["StoryVersion"] = relationship(back_populates="judgements")


class Image(Base):
    __tablename__ = "images"

    id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=False, index=True)
    story_version_id: Mapped[uuid.UUID | None] = mapped_column(sa.UUID(as_uuid=True), sa.ForeignKey("story_versions.id"), nullable=True)
    # "scene" | "cover"
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    scene_index: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    prompt: Mapped[str] = mapped_column(sa.Text, nullable=False)
    provider: Mapped[str] = mapped_column(sa.Text, nullable=False)
    provider_params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    seed: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    storage_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


class CharacterAsset(Base):
    __tablename__ = "character_assets"

    id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=False, index=True)
    # "reference_images" (v1) | "trained_model" (future)
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)

    book: Mapped["Book"] = relationship(back_populates="character_assets")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=False, index=True)
    from_status: Mapped[BookStatus | None] = mapped_column(_bookstatus_col, nullable=True)
    to_status: Mapped[BookStatus] = mapped_column(_bookstatus_col, nullable=False)
    # "orchestrator" | "human"
    actor: Mapped[str] = mapped_column(sa.Text, nullable=False)
    note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)

    book: Mapped["Book"] = relationship(back_populates="audit_log")
