"""Repository for the judgements table."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Judgement


class JudgementRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(
        self,
        book_id: uuid.UUID,
        story_version_id: uuid.UUID,
        round: int,
        judge_prompt_version: str,
        *,
        emotional_authenticity: float,
        representation_quality: float,
        pacing: float,
        age_fit: float,
        uniqueness: float,
        weighted_total: float,
        passed: bool,
        critique: dict,
    ) -> Judgement:
        judgement = Judgement(
            book_id=book_id,
            story_version_id=story_version_id,
            round=round,
            judge_prompt_version=judge_prompt_version,
            emotional_authenticity=emotional_authenticity,
            representation_quality=representation_quality,
            pacing=pacing,
            age_fit=age_fit,
            uniqueness=uniqueness,
            weighted_total=weighted_total,
            passed=passed,
            critique=critique,
        )
        self._s.add(judgement)
        self._s.flush()
        return judgement

    def list_for_round(self, book_id: uuid.UUID, round: int) -> list[Judgement]:
        stmt = (
            select(Judgement)
            .where(Judgement.book_id == book_id, Judgement.round == round)
            .order_by(Judgement.weighted_total.desc())
        )
        return list(self._s.scalars(stmt))

    def best_for_round(self, book_id: uuid.UUID, round: int) -> Judgement | None:
        results = self.list_for_round(book_id, round)
        return results[0] if results else None
