"""Repository for the character_assets table."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CharacterAsset


class CharacterAssetRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, book_id: uuid.UUID, kind: str, data: dict) -> CharacterAsset:
        asset = CharacterAsset(book_id=book_id, kind=kind, data=data)
        self._s.add(asset)
        self._s.flush()
        return asset

    def list_for_book(self, book_id: uuid.UUID) -> list[CharacterAsset]:
        stmt = select(CharacterAsset).where(CharacterAsset.book_id == book_id).order_by(CharacterAsset.created_at)
        return list(self._s.scalars(stmt))
