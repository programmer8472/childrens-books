"""Repository for the images table."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Image


class ImageRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(
        self,
        book_id: uuid.UUID,
        kind: str,
        prompt: str,
        provider: str,
        provider_params: dict,
        storage_key: str,
        *,
        story_version_id: uuid.UUID | None = None,
        scene_index: int | None = None,
        seed: str | None = None,
    ) -> Image:
        image = Image(
            book_id=book_id,
            story_version_id=story_version_id,
            kind=kind,
            scene_index=scene_index,
            prompt=prompt,
            provider=provider,
            provider_params=provider_params,
            seed=seed,
            storage_key=storage_key,
        )
        self._s.add(image)
        self._s.flush()
        return image

    def list_for_book(self, book_id: uuid.UUID, *, kind: str | None = None) -> list[Image]:
        stmt = select(Image).where(Image.book_id == book_id)
        if kind is not None:
            stmt = stmt.where(Image.kind == kind)
        stmt = stmt.order_by(Image.scene_index.nulls_last(), Image.created_at)
        return list(self._s.scalars(stmt))
