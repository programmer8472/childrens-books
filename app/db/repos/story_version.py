"""Repository for the story_versions table (append-only)."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import StoryVersion


class StoryVersionRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(
        self,
        book_id: uuid.UUID,
        round: int,
        method: str,
        content: str,
        *,
        spreads: list | None = None,
        prior_critique: str | None = None,
    ) -> StoryVersion:
        version = StoryVersion(
            book_id=book_id,
            round=round,
            method=method,
            content=content,
            spreads=spreads,
            prior_critique=prior_critique,
        )
        self._s.add(version)
        self._s.flush()
        return version

    def get(self, version_id: uuid.UUID) -> StoryVersion:
        version = self._s.get(StoryVersion, version_id)
        if version is None:
            raise ValueError(f"StoryVersion {version_id} not found")
        return version

    def list_for_book(self, book_id: uuid.UUID) -> list[StoryVersion]:
        stmt = (
            select(StoryVersion)
            .where(StoryVersion.book_id == book_id)
            .order_by(StoryVersion.created_at)
        )
        return list(self._s.scalars(stmt))

    def list_for_round(self, book_id: uuid.UUID, round: int) -> list[StoryVersion]:
        stmt = (
            select(StoryVersion)
            .where(StoryVersion.book_id == book_id, StoryVersion.round == round)
            .order_by(StoryVersion.created_at)
        )
        return list(self._s.scalars(stmt))

    def set_shortlisted(self, version_id: uuid.UUID, shortlisted: bool) -> None:
        version = self.get(version_id)
        version.shortlisted = shortlisted
        self._s.flush()

    def list_shortlisted_for_book(self, book_id: uuid.UUID) -> list[StoryVersion]:
        stmt = (
            select(StoryVersion)
            .where(StoryVersion.book_id == book_id, StoryVersion.shortlisted.is_(True))
            .order_by(StoryVersion.created_at)
        )
        return list(self._s.scalars(stmt))
