"""Pipeline orchestrator.

Owns all state-machine sequencing and is the only caller of BookRepo.transition().
Agents own thinking; this class owns the order of operations and the DB writes.
"""
import uuid

from app.agents.base import check_spread_budget
from app.agents.judge import JudgeAgent
from app.agents.metadata import MetadataAgent
from app.agents.writer import WriterAgent
from app.db.enums import BookStatus
from app.db.repos import BookRepo, ImageRepo, JudgementRepo, StoryVersionRepo
from app.providers.base import CharacterRef, ImageProvider, LLMProvider
from app.storage.local import LocalStorage

# Brief keys passed to the judge as scoring context. These must match the keys
# the create-book form actually sends (app/api/books.py CreateBookIn.brief), or
# the judge silently scores with no context.
_WRITING_METHODS = ("three-act", "sensory-first", "problem-solution", "hero's-journey")
_CRITERIA_KEYS = ("age_range", "theme", "characters", "setting")
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
        """Score all versions for the current round; advance to AWAITING_SHORTLIST or REVISION."""
        book = self._books.get(book_id)
        versions = self._versions.list_for_round(book_id, book.current_round)

        judge = JudgeAgent(self._llm, threshold=book.score_threshold)
        criteria = {k: book.brief[k] for k in _CRITERIA_KEYS if k in book.brief}
        results = judge.judge([v.content for v in versions], criteria)

        # Idempotent: replace any prior judgements for this round so a retried
        # or re-delivered task doesn't accumulate duplicate rows.
        self._judgements.delete_for_versions(
            book.id, book.current_round, [v.id for v in versions]
        )
        age_range = book.brief.get("age_range", "3-8")
        for version, result in zip(versions, results):
            self._apply_budget_gate(version, result, age_range)
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

        if outcome == "shortlist":
            self._books.transition(book, BookStatus.AWAITING_SHORTLIST, actor="orchestrator")
        else:
            self._books.transition(book, BookStatus.REVISION, actor="orchestrator")

    def handle_revision(self, book_id: uuid.UUID) -> None:
        """REVISION → WRITING; increment round; run next writing round."""
        book = self._books.get(book_id)
        self._books.transition(book, BookStatus.WRITING, actor="orchestrator")
        self._books.increment_round(book)
        self._run_writing_round(book)

    def rejudge_shortlist(self, book_id: uuid.UUID, story_version_ids: list[uuid.UUID]) -> None:
        """AWAITING_SHORTLIST → SHORTLIST_JUDGING → AWAITING_FINAL_APPROVAL.

        Re-runs JudgeAgent on the human-selected subset of versions and stores
        fresh judgements so the final-approval view shows up-to-date scores.
        """
        book = self._books.get(book_id)
        self._books.transition(book, BookStatus.SHORTLIST_JUDGING, actor="orchestrator")

        for vid in story_version_ids:
            self._versions.set_shortlisted(vid, True)

        versions = [self._versions.get(vid) for vid in story_version_ids]
        judge = JudgeAgent(self._llm, threshold=book.score_threshold)
        criteria = {k: book.brief[k] for k in _CRITERIA_KEYS if k in book.brief}
        results = judge.judge([v.content for v in versions], criteria)

        # Idempotent: replace prior scores for these versions in this round.
        self._judgements.delete_for_versions(book.id, book.current_round, story_version_ids)
        age_range = book.brief.get("age_range", "3-8")
        for version, result in zip(versions, results):
            self._apply_budget_gate(version, result, age_range)
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

        self._books.transition(book, BookStatus.AWAITING_FINAL_APPROVAL, actor="orchestrator")

    def generate_images(self, book_id: uuid.UUID, event_cb=None) -> None:
        """APPROVED → GENERATING_IMAGES; generate 12 interior scene images."""
        from app.compositor.spread_types import assign_spread_types, NUM_STORY_SPREADS
        book = self._books.get(book_id)
        self._books.transition(book, BookStatus.GENERATING_IMAGES, actor="orchestrator")

        _, spreads, _ = self._get_approved_story(book)

        char_ref = CharacterRef(kind="reference_images", data={})
        spread_types = assign_spread_types()
        scene_prompts = self._derive_scene_prompts(spreads, book.brief, spread_types)

        for i, (prompt, spread_type) in enumerate(zip(scene_prompts, spread_types)):
            # Mid-stage cancel: a human stop request set during the long image
            # loop aborts here rather than only at the next stage boundary. The
            # transition to CANCELLED is left to the task guard (single owner).
            if getattr(self._books, "refresh", None):
                self._books.refresh(book)
            if getattr(book, "cancel_requested", False):
                return
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
        story_text, _, _ = self._get_approved_story(book)
        agent = MetadataAgent(self._llm)
        metadata = agent.draft(story_text, book.brief)
        self._books.save_metadata(book, metadata)
        self._books.transition(book, BookStatus.EXPORTING, actor="orchestrator")

    def export_book(self, book_id: uuid.UUID) -> None:
        """EXPORTING → EXPORT_READY; compose all files, then gate on preflight QA."""
        from app.compositor.composer import BookComposer
        from app.compositor.preflight import validate_interior
        book = self._books.get(book_id)
        story_text, spreads, _ = self._get_approved_story(book)
        metadata = book.book_metadata or {}

        scene_images_db = self._images.list_for_book(book_id, kind="scene")
        cover_images_db = self._images.list_for_book(book_id, kind="cover")

        interior_images: list[bytes | None] = [None] * _NUM_SPREADS
        for img in scene_images_db:
            if img.scene_index is not None and img.scene_index < _NUM_SPREADS:
                if self._storage.exists(img.storage_key):
                    interior_images[img.scene_index] = self._storage.get(img.storage_key)

        cover_bytes: bytes | None = None
        if cover_images_db:
            key = cover_images_db[-1].storage_key
            if self._storage.exists(key):
                cover_bytes = self._storage.get(key)

        composer = BookComposer(self._storage)
        manifest = composer.compose_all(
            book_id, story_text, interior_images, cover_bytes, metadata, spreads=spreads
        )

        # QA gate: never declare a clipped or out-of-spec book EXPORT_READY.
        interior_pdf = self._storage.get(manifest["interior_pdf"])
        report = validate_interior(spreads, interior_images, metadata, interior_pdf)
        manifest["preflight"] = report.to_dict()
        self._books.save_export_manifest(book, manifest)

        if not report.passed:
            self._books.fail(book, note=f"Export preflight failed: {report.summary()}")
            return

        self._books.transition(book, BookStatus.EXPORT_READY, actor="orchestrator")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_writing_round(self, book) -> None:
        """Write all methods for book.current_round; idempotent per (book, round, method)."""
        writer = WriterAgent(self._llm)
        existing_methods = {
            v.method for v in self._versions.list_for_round(book.id, book.current_round)
        }
        judge_critique = self._get_round_critique(book.id, book.current_round)
        prev_by_method = {
            v.method: v
            for v in self._versions.list_for_round(book.id, book.current_round - 1)
        } if book.current_round > 1 else {}

        for method in _WRITING_METHODS:
            if method in existing_methods:
                continue
            prior_critique = None
            if judge_critique and method in prev_by_method:
                own_draft = prev_by_method[method].content
                prior_critique = f"PREVIOUS DRAFT:\n{own_draft}\n\nJUDGE CRITIQUE:\n{judge_critique}"
            draft = writer.write(book.brief, method, prior_critique)
            self._versions.create(
                book_id=book.id,
                round=book.current_round,
                method=method,
                content=draft.content,
                spreads=draft.spreads,
                prior_critique=prior_critique,
            )

        self._books.transition(book, BookStatus.JUDGING, actor="orchestrator")

    def _spreads_for(self, version) -> list[str]:
        """Return a version's 12 spread strings, paginating content for legacy rows."""
        if getattr(version, "spreads", None):
            return list(version.spreads)
        from app.compositor.pdf_writer import _split_story
        return _split_story(version.content or "", _NUM_SPREADS)

    def _apply_budget_gate(self, version, result, age_range: str) -> None:
        """Deterministically fail any version whose spreads exceed the word cap.

        Word counts are computed here (not trusted to the LLM). On violation we
        force passed=False and fold a concrete instruction into the age_fit
        critique so the next writing round shortens the offending spreads.
        """
        violations = check_spread_budget(self._spreads_for(version), age_range)
        if not violations:
            return
        result.passed = False
        note = " ".join(v.message() for v in violations[:3])
        existing = result.critique.get("age_fit", "")
        result.critique = {
            **result.critique,
            "age_fit": f"{existing} LENGTH FAIL: {note}".strip(),
        }

    def _decide_outcome(self, book, best_judgement) -> str:
        """Return 'shortlist' or 'retry'.

        All max_rounds are always run before handing off to the human shortlist
        gate — no early exit on score pass.
        """
        if book.current_round >= book.max_rounds:
            return "shortlist"
        return "retry"

    def _get_approved_story(self, book) -> tuple[str, list[str], uuid.UUID | None]:
        """Return (story_text, spreads, version_id) for post-approval stages.

        Uses book.approved_version_id when set (new three-phase flow), falling
        back to best_for_round for books approved via the legacy AWAITING_APPROVAL gate.
        """
        if getattr(book, "approved_version_id", None):
            version = self._versions.get(book.approved_version_id)
        else:
            best = self._judgements.best_for_round(book.id, book.current_round)
            version = self._versions.get(best.story_version_id) if best else None

        # Post-approval stages (images, metadata, export) cannot run on an empty
        # story. Fail loudly so the book retires with a clear reason rather than
        # silently producing a blank book.
        if version is None or not (version.content or "").strip():
            raise RuntimeError(
                f"No approved story content for book {book.id} "
                f"(status={book.status.value}, round={book.current_round})"
            )
        return version.content, self._spreads_for(version), version.id

    def _derive_scene_prompts(self, spreads: list[str], brief: dict, spread_types) -> list[str]:
        """Build 12 scene prompts, one per spread, from the structured spread text."""
        genre = brief.get("genre", "children's picture book")
        age = brief.get("age_range", "3-8")
        art_style = brief.get("art_style", "warm, colorful, digital illustration")
        return [
            f"{art_style}, {genre}, ages {age}. Scene: {seg[:200]}" if seg else
            f"{art_style}, {genre}, ages {age}. Illustration for a children's book."
            for seg in spreads
        ]

    def _get_round_critique(self, book_id: uuid.UUID, current_round: int) -> str | None:
        """Return judge critique lines from the best judgement in the previous round."""
        if current_round <= 1:
            return None
        best_judgement = self._judgements.best_for_round(book_id, current_round - 1)
        if best_judgement is None:
            return None
        return "\n".join(
            f"- {dim}: {text}" for dim, text in best_judgement.critique.items()
        )
