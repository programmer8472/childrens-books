"""Repository for the books table."""
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.enums import BookStatus, assert_legal_transition
from app.db.models import AuditLog, Book


class BookRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, brief: dict, *, title: str | None = None, max_rounds: int = 5, score_threshold: float = 7.5) -> Book:
        book = Book(
            brief=brief,
            title=title,
            status=BookStatus.DRAFT_BRIEF,
            max_rounds=max_rounds,
            score_threshold=score_threshold,
        )
        self._s.add(book)
        audit = AuditLog(
            book=book,
            from_status=None,
            to_status=BookStatus.DRAFT_BRIEF,
            actor="orchestrator",
        )
        self._s.add(audit)
        self._s.flush()
        return book

    def get(self, book_id: uuid.UUID) -> Book:
        book = self._s.get(Book, book_id)
        if book is None:
            raise ValueError(f"Book {book_id} not found")
        return book

    def transition(self, book: Book, to_status: BookStatus, *, actor: str, note: str | None = None) -> Book:
        assert_legal_transition(book.status, to_status)
        audit = AuditLog(
            book_id=book.id,
            from_status=book.status,
            to_status=to_status,
            actor=actor,
            note=note,
        )
        book.status = to_status
        book.updated_at = datetime.now()
        self._s.add(audit)
        self._s.flush()
        return book

    def increment_round(self, book: Book) -> Book:
        book.current_round += 1
        book.updated_at = datetime.now()
        self._s.flush()
        return book
