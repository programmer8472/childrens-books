"""Pipeline orchestrator.

Owns all state-machine sequencing and is the only caller of BookRepo.transition().
Agents own thinking; this class owns the order of operations and the DB writes.
"""
import uuid

from app.agents.judge import JudgeAgent
from app.agents.metadata import MetadataAgent
from app.agents.writer import WriterAgent
from app.db.enums import BookStatus
from app.db.repos import BookRepo, ImageRepo, JudgementRepo, StoryVersionRepo
from app.providers.base import CharacterRef, ImageProvider, LLMProvider
from app.storage.local import LocalStorage

_WRITING_METHODS = ("three-act", "sensory-first", "problem-solution", "hero's-journey")
_CRITERIA_KEYS = ("age_range", "genre", "themes")
_NUM_SPREADS = 12


class Orchestrator:
    def __init__(
        self,
        book_repo: BookRepo,
        version_repo: StoryVersionRepo,
        judgement_repo: JudgementRepo,
        image_repo: ImageRepo,
        llm: LLMProvider,
        image: ImageProvider,
        storage: LocalStorage,
    ) -> None:
        self._books = book_repo
        self._versions = version_repo
        self._judgements = judgement_repo
        self._images = image_repo
        self._llm = llm
        self._image = image
        self._storage = storage

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

    def generate_images(self, book_id: uuid.UUID, event_cb=None) -> None:
        """APPROVED → GENERATING_IMAGES; generate 12 interior scene images."""
        from app.compositor.spread_types import assign_spread_types, NUM_STORY_SPREADS
        book = self._books.get(book_id)
        self._books.transition(book, BookStatus.GENERATING_IMAGES, actor="orchestrator")

        best_judgement = self._judgements.best_for_round(book_id, book.current_round)
        version = self._versions.get(best_judgement.story_version_id) if best_judgement else None
        story_text = version.content if version else ""

        char_ref = CharacterRef(kind="reference_images", data={})
        spread_types = assign_spread_types()
        scene_prompts = self._derive_scene_prompts(story_text, book.brief, spread_types)

        for i, (prompt, spread_type) in enumerate(zip(scene_prompts, spread_types)):
            params = {"spread_type": spread_type.value, "scene_index": i}
            result = self._image.generate_scene(prompt, char_ref, params)
            self._images.create(
                book_id=book_id,
                kind="scene",
                prompt=prompt,
                provider=type(self._image).__name__,
                provider_params=result.provider_params,
                storage_key=result.storage_key,
                scene_index=i,
                seed=result.seed,
            )
            if event_cb:
                event_cb(i + 1, NUM_STORY_SPREADS)

        self._books.transition(book, BookStatus.GENERATING_COVER, actor="orchestrator")

    def generate_cover(self, book_id: uuid.UUID) -> None:
        """GENERATING_COVER → DRAFTING_METADATA; generate cover image and store it."""
        book = self._books.get(book_id)
        char_ref = CharacterRef(kind="reference_images", data={})
        title = (book.book_metadata or {}).get("title") or book.brief.get("title", "")
        prompt = f"Front cover illustration for a children's book titled '{title}'. " \
                 "Bold, warm, inviting. Character centered. High contrast for thumbnail readability."
        params = {"spread_type": "COVER", "scene_index": -1}
        result = self._image.generate_scene(prompt, char_ref, params)
        self._images.create(
            book_id=book_id,
            kind="cover",
            prompt=prompt,
            provider=type(self._image).__name__,
            provider_params=result.provider_params,
            storage_key=result.storage_key,
            scene_index=None,
            seed=result.seed,
        )
        self._books.transition(book, BookStatus.DRAFTING_METADATA, actor="orchestrator")

    def draft_metadata(self, book_id: uuid.UUID) -> None:
        """DRAFTING_METADATA → EXPORTING; draft title/description/keywords via LLM."""
        book = self._books.get(book_id)
        best_judgement = self._judgements.best_for_round(book_id, book.current_round)
        version = self._versions.get(best_judgement.story_version_id) if best_judgement else None
        story_text = version.content if version else ""
        agent = MetadataAgent(self._llm)
        metadata = agent.draft(story_text, book.brief)
        self._books.save_metadata(book, metadata)
        self._books.transition(book, BookStatus.EXPORTING, actor="orchestrator")

    def export_book(self, book_id: uuid.UUID) -> None:
        """EXPORTING → EXPORT_READY; run the compositor and write all export files."""
        from app.compositor.composer import BookComposer
        book = self._books.get(book_id)
        best_judgement = self._judgements.best_for_round(book_id, book.current_round)
        version = self._versions.get(best_judgement.story_version_id) if best_judgement else None
        story_text = version.content if version else ""
        metadata = book.book_metadata or {}

        scene_images_db = self._images.list_for_book(book_id, kind="scene")
        cover_images_db = self._images.list_for_book(book_id, kind="cover")

        interior_images: list[bytes | None] = [None] * 12
        for img in scene_images_db:
            if img.scene_index is not None and img.scene_index < 12:
                if self._storage.exists(img.storage_key):
                    interior_images[img.scene_index] = self._storage.get(img.storage_key)

        cover_bytes: bytes | None = None
        if cover_images_db:
            key = cover_images_db[-1].storage_key
            if self._storage.exists(key):
                cover_bytes = self._storage.get(key)

        composer = BookComposer(self._storage)
        manifest = composer.compose_all(book_id, story_text, interior_images, cover_bytes, metadata)
        self._books.save_export_manifest(book, manifest)
        self._books.transition(book, BookStatus.EXPORT_READY, actor="orchestrator")

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

    def _derive_scene_prompts(self, story_text: str, brief: dict, spread_types) -> list[str]:
        """Split story into 12 scene prompts, one per spread."""
        from app.compositor.pdf_writer import _split_story
        genre = brief.get("genre", "children's picture book")
        age = brief.get("age_range", "3-8")
        art_style = brief.get("art_style", "warm, colorful, digital illustration")
        segments = _split_story(story_text, 12)
        return [
            f"{art_style}, {genre}, ages {age}. Scene: {seg[:200]}" if seg else
            f"{art_style}, {genre}, ages {age}. Illustration for a children's book."
            for seg in segments
        ]

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
