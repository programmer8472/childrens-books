"""Pipeline orchestrator.

Owns all state-machine sequencing and is the only caller of BookRepo.transition().
Agents own thinking; this class owns the order of operations and the DB writes.
"""
import uuid

from app.agents.judge import JudgeAgent
from app.agents.writer import WriterAgent
from app.db.enums import BookStatus
from app.db.repos import BookRepo, JudgementRepo, StoryVersionRepo
from app.providers.base import ImageProvider, LLMProvider

_WRITING_METHODS = ("three-act", "sensory-first", "problem-solution", "hero's-journey")
_CRITERIA_KEYS = ("age_range", "genre", "themes")


class Orchestrator:
    def __init__(
        self,
        book_repo: BookRepo,
        version_repo: StoryVersionRepo,
        judgement_repo: JudgementRepo,
        llm: LLMProvider,
        image: ImageProvider,
    ) -> None:
        self._books = book_repo
        self._versions = version_repo
        self._judgements = judgement_repo
        self._llm = llm
        self._image = image

    # ------------------------------------------------------------------
    # Public pipeline steps (each maps to a Celery task in tasks.py)
    # ------------------------------------------------------------------

    def start(self, book_id: uuid.UUID) -> None:
        """DRAFT_BRIEF → OUTLINING → WRITING; start round 1."""
        book = self._books.get(book_id)
        self._books.transition(book, BookStatus.OUTLINING, actor="orchestrator")
        # OUTLINING is a placeholder for future outline generation; pass through immediately.
        self._books.transition(book, BookStatus.WRITING, actor="orchestrator")
        self._books.increment_round(book)
        self._run_writing_round(book)

    def run_judging(self, book_id: uuid.UUID) -> None:
        """Score all versions for the current round; advance to AWAITING_APPROVAL, REVISION, or RETIRED."""
        book = self._books.get(book_id)
        versions = self._versions.list_for_round(book_id, book.current_round)

        judge = JudgeAgent(self._llm, threshold=book.score_threshold)
        criteria = {k: book.brief[k] for k in _CRITERIA_KEYS if k in book.brief}
        results = judge.judge([v.content for v in versions], criteria)

        for version, result in zip(versions, results):
            self._judgements.create(
                book_id=book.id,
                story_version_id=version.id,
                round=book.current_round,
                judge_prompt_version=JudgeAgent.PROMPT_VERSION,
                emotional_authenticity=result.emotional_authenticity,
                representation_quality=result.representation_quality,
                pacing=result.pacing,
                age_fit=result.age_fit,
                uniqueness=result.uniqueness,
                weighted_total=result.weighted_total,
                passed=result.passed,
                critique=result.critique,
            )

        best = self._judgements.best_for_round(book_id, book.current_round)
        outcome = self._decide_outcome(book, best)

        if outcome == "pass":
            self._books.transition(book, BookStatus.AWAITING_APPROVAL, actor="orchestrator")
        elif outcome == "retry":
            self._books.transition(book, BookStatus.REVISION, actor="orchestrator")
        else:
            self._books.transition(
                book, BookStatus.RETIRED, actor="orchestrator",
                note=f"Max rounds ({book.max_rounds}) reached without passing threshold "
                     f"({book.score_threshold}). Best score: {best.weighted_total if best else 'n/a'}.",
            )

    def handle_revision(self, book_id: uuid.UUID) -> None:
        """REVISION → WRITING; increment round; run next writing round."""
        book = self._books.get(book_id)
        self._books.transition(book, BookStatus.WRITING, actor="orchestrator")
        self._books.increment_round(book)
        self._run_writing_round(book)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_writing_round(self, book) -> None:
        """Write all methods for book.current_round; idempotent per (book, round, method)."""
        writer = WriterAgent(self._llm)
        prior_critique = self._build_prior_critique(book.id, book.current_round)
        existing_methods = {
            v.method for v in self._versions.list_for_round(book.id, book.current_round)
        }

        for method in _WRITING_METHODS:
            if method in existing_methods:
                continue
            content = writer.write(book.brief, method, prior_critique)
            self._versions.create(
                book_id=book.id,
                round=book.current_round,
                method=method,
                content=content,
                prior_critique=prior_critique,
            )

        self._books.transition(book, BookStatus.JUDGING, actor="orchestrator")

    def _decide_outcome(self, book, best_judgement) -> str:
        """Return 'pass', 'retry', or 'retire' given the current book state and best score."""
        if best_judgement is not None and best_judgement.passed:
            return "pass"
        if book.current_round >= book.max_rounds:
            return "retire"
        return "retry"

    def _build_prior_critique(self, book_id: uuid.UUID, current_round: int) -> str | None:
        """Combine the best version + its critique from the previous round into one string."""
        if current_round <= 1:
            return None
        best_judgement = self._judgements.best_for_round(book_id, current_round - 1)
        if best_judgement is None:
            return None
        version = self._versions.get(best_judgement.story_version_id)
        critique_lines = "\n".join(
            f"- {dim}: {text}" for dim, text in best_judgement.critique.items()
        )
        return f"PREVIOUS DRAFT:\n{version.content}\n\nJUDGE CRITIQUE:\n{critique_lines}"
