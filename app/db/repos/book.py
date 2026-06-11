"""Repository for the books table."""
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import LEGAL_TRANSITIONS, BookStatus, assert_legal_transition
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

    def fail(self, book: Book, note: str) -> Book | None:
        """Mark a book RETIRED after a stage exhausted its retries.

        Returns the book, or None if RETIRED isn't a legal target from its
        current state (e.g. it already reached a human gate or terminal state) —
        in that case we leave it untouched rather than raise from a failure path.
        """
        if BookStatus.RETIRED not in LEGAL_TRANSITIONS.get(book.status, frozenset()):
            return None
        return self.transition(book, BookStatus.RETIRED, actor="orchestrator", note=note)

    def refresh(self, book: Book) -> Book:
        """Re-read the row from the DB (sees other committed transactions)."""
        self._s.refresh(book)
        return book

    def request_cancel(self, book: Book) -> Book:
        """Flag a running book for cancellation; the stage guard does the rest."""
        book.cancel_requested = True
        book.updated_at = datetime.now()
        self._s.flush()
        return book

    def cancel(self, book: Book, note: str | None = None) -> Book | None:
        """Transition a book to CANCELLED (human stop). No-op if not legal."""
        if BookStatus.CANCELLED not in LEGAL_TRANSITIONS.get(book.status, frozenset()):
            return None
        return self.transition(book, BookStatus.CANCELLED, actor="human", note=note)

    def list_all(self) -> list[Book]:
        stmt = select(Book).order_by(Book.created_at.desc())
        return list(self._s.scalars(stmt))

    def increment_round(self, book: Book) -> Book:
        book.current_round += 1
        book.updated_at = datetime.now()
        self._s.flush()
        return book

    def save_metadata(self, book: Book, metadata: dict) -> Book:
        book.book_metadata = metadata
        book.updated_at = datetime.now()
        self._s.flush()
        return book

    def save_export_manifest(self, book: Book, manifest: dict) -> Book:
        book.export_manifest = manifest
        book.updated_at = datetime.now()
        self._s.flush()
        return book

    def set_approved_version(self, book: Book, version_id: uuid.UUID) -> Book:
        book.approved_version_id = version_id
        book.updated_at = datetime.now()
        self._s.flush()
        return book
