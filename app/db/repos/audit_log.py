"""Repository for the audit_log table (append-only — no update/delete)."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog


class AuditLogRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def list_for_book(self, book_id: uuid.UUID) -> list[AuditLog]:
        stmt = select(AuditLog).where(AuditLog.book_id == book_id).order_by(AuditLog.created_at)
        return list(self._s.scalars(stmt))
