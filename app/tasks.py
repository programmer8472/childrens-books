"""Celery tasks.

Each pipeline task does exactly one step, commits, then enqueues the next.
Tasks are idempotent: re-running a task for the same (book_id, round, method)
is safe — the orchestrator skips work already done.
"""
import uuid

from celery import Task

from app.celery_app import celery_app
from app.config import get_settings
from app.db.repos import BookRepo, ImageRepo, JudgementRepo, StoryVersionRepo
from app.db.session import get_task_session
from app.events import publish_event
from app.orchestrator import Orchestrator
from app.providers.factory import get_image_provider, get_llm_provider
from app.storage.local import LocalStorage

# Retry policy for every pipeline stage. Generous enough that a transient
# provider blip (DeepSeek timeout, brief network drop) recovers on its own
# rather than killing a book that already cost minutes of LLM work.
_MAX_RETRIES = 6
_BACKOFF_BASE = 5  # seconds; doubles each attempt
_BACKOFF_CAP = 120


def _retry_countdown(task: Task) -> int:
    """Exponential backoff with a ceiling, based on the current attempt."""
    return min(_BACKOFF_CAP, _BACKOFF_BASE * (2 ** task.request.retries))


class PipelineTask(Task):
    """Base for pipeline tasks: on terminal failure, retire the book loudly.

    When a stage exhausts its retries, Celery calls on_failure. We mark the
    book RETIRED with the error in the audit note and publish a `failed` event,
    so a dead pipeline shows up red on the board with a reason instead of
    silently freezing in an in-progress state.
    """

    def on_failure(self, exc, task_id, args, kwargs, einfo):  # noqa: ANN001
        book_id = kwargs.get("book_id") or (args[0] if args else None)
        if not book_id:
            return
        reason = f"{type(exc).__name__}: {exc}"
        try:
            _id = uuid.UUID(str(book_id))
            with get_task_session() as session:
                repo = BookRepo(session)
                book = repo.get(_id)
                failed_from = book.status.value
                retired = repo.fail(book, note=f"Failed during {failed_from}: {reason}")
            if retired is not None:
                publish_event(
                    _id,
                    {"type": "failed", "status": "RETIRED", "stage": failed_from,
                     "actor": "orchestrator", "error": reason},
                )
        except Exception:
            # A failure-handling failure must never mask the original error.
            pass


def _make_orchestrator(session):
    settings = get_settings()
    return Orchestrator(
        book_repo=BookRepo(session),
        version_repo=StoryVersionRepo(session),
        judgement_repo=JudgementRepo(session),
        image_repo=ImageRepo(session),
        llm=get_llm_provider(),
        image=get_image_provider(),
        storage=LocalStorage(settings.storage_local_root),
    )


def _emit(book_id: uuid.UUID, status: str, round_: int, actor: str = "orchestrator") -> None:
    publish_event(book_id, {"type": "status_change", "status": status, "round": round_, "actor": actor})


def _emit_progress(book_id: uuid.UUID, current: int, total: int, stage: str) -> None:
    publish_event(book_id, {"type": "progress", "stage": stage, "current": current, "total": total})


def _check_cancelled(session, book_id: uuid.UUID) -> bool:
    """If a human requested cancel, mark the book CANCELLED and stop the chain.

    Called at the top of every pipeline task — the natural stage boundary. Returns
    True when the book was cancelled (caller must return without enqueuing the
    next stage); False to proceed normally.
    """
    repo = BookRepo(session)
    book = repo.get(book_id)
    if not book.cancel_requested:
        return False
    if repo.cancel(book, note="Cancelled by human") is None:
        return False  # not a legal target (already terminal) — let it proceed
    publish_event(book_id, {"type": "cancelled", "status": "CANCELLED", "actor": "human"})
    return True


# ---------------------------------------------------------------------------
# Diagnostic
# ---------------------------------------------------------------------------

@celery_app.task(name="app.tasks.ping")
def ping() -> str:
    """Trivial round-trip check: enqueue this, get 'pong' back from a worker."""
    return "pong"


# ---------------------------------------------------------------------------
# Pipeline — writing/judging loop
# ---------------------------------------------------------------------------

@celery_app.task(name="app.tasks.pipeline_start", base=PipelineTask, bind=True, max_retries=_MAX_RETRIES)
def pipeline_start(self, book_id: str) -> None:
    """Kick off a book: DRAFT_BRIEF → OUTLINING → WRITING → JUDGING."""
    _id = uuid.UUID(book_id)
    try:
        with get_task_session() as session:
            if _check_cancelled(session, _id):
                return
            _make_orchestrator(session).start(_id)
            book = BookRepo(session).get(_id)
            status, round_ = book.status.value, book.current_round
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_retry_countdown(self))
    _emit(_id, status, round_)
    pipeline_run_judging.delay(book_id)


@celery_app.task(name="app.tasks.pipeline_run_judging", base=PipelineTask, bind=True, max_retries=_MAX_RETRIES)
def pipeline_run_judging(self, book_id: str) -> None:
    """Judge current-round versions; advance to AWAITING_SHORTLIST or REVISION."""
    _id = uuid.UUID(book_id)
    try:
        with get_task_session() as session:
            if _check_cancelled(session, _id):
                return
            orch = _make_orchestrator(session)
            orch.run_judging(_id)
            book = BookRepo(session).get(_id)
            status, round_ = book.status.value, book.current_round
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_retry_countdown(self))
    _emit(_id, status, round_)
    if status == "REVISION":
        pipeline_handle_revision.delay(book_id)
    # AWAITING_SHORTLIST → pause here; human selects shortlist via POST /shortlist


@celery_app.task(name="app.tasks.pipeline_handle_revision", base=PipelineTask, bind=True, max_retries=_MAX_RETRIES)
def pipeline_handle_revision(self, book_id: str) -> None:
    """REVISION → WRITING; increment round; run next writing round."""
    _id = uuid.UUID(book_id)
    try:
        with get_task_session() as session:
            if _check_cancelled(session, _id):
                return
            _make_orchestrator(session).handle_revision(_id)
            book = BookRepo(session).get(_id)
            status, round_ = book.status.value, book.current_round
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_retry_countdown(self))
    _emit(_id, status, round_)
    pipeline_run_judging.delay(book_id)


@celery_app.task(name="app.tasks.pipeline_rejudge_shortlist", base=PipelineTask, bind=True, max_retries=_MAX_RETRIES)
def pipeline_rejudge_shortlist(self, book_id: str, story_version_ids: list[str]) -> None:
    """AWAITING_SHORTLIST → SHORTLIST_JUDGING → AWAITING_FINAL_APPROVAL."""
    _id = uuid.UUID(book_id)
    version_ids = [uuid.UUID(v) for v in story_version_ids]
    try:
        with get_task_session() as session:
            if _check_cancelled(session, _id):
                return
            _make_orchestrator(session).rejudge_shortlist(_id, version_ids)
            book = BookRepo(session).get(_id)
            status, round_ = book.status.value, book.current_round
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_retry_countdown(self))
    _emit(_id, status, round_)
    # AWAITING_FINAL_APPROVAL → pause; human picks one version via POST /approve


# ---------------------------------------------------------------------------
# Pipeline — post-approval stages
# ---------------------------------------------------------------------------

@celery_app.task(name="app.tasks.pipeline_generate_images", base=PipelineTask, bind=True, max_retries=_MAX_RETRIES)
def pipeline_generate_images(self, book_id: str) -> None:
    """APPROVED → GENERATING_IMAGES; generate 12 interior scene images."""
    _id = uuid.UUID(book_id)
    try:
        with get_task_session() as session:
            if _check_cancelled(session, _id):
                return

            def _cb(current, total):
                _emit_progress(_id, current, total, "GENERATING_IMAGES")

            _make_orchestrator(session).generate_images(_id, event_cb=_cb)
            # generate_images returns early (without transitioning) if a cancel
            # was requested mid-loop; finalize that into CANCELLED here.
            if _check_cancelled(session, _id):
                return
            book = BookRepo(session).get(_id)
            status, round_ = book.status.value, book.current_round
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_retry_countdown(self))
    _emit(_id, status, round_)
    pipeline_generate_cover.delay(book_id)


@celery_app.task(name="app.tasks.pipeline_generate_cover", base=PipelineTask, bind=True, max_retries=_MAX_RETRIES)
def pipeline_generate_cover(self, book_id: str) -> None:
    """GENERATING_COVER → DRAFTING_METADATA; generate cover image."""
    _id = uuid.UUID(book_id)
    try:
        with get_task_session() as session:
            if _check_cancelled(session, _id):
                return
            _make_orchestrator(session).generate_cover(_id)
            book = BookRepo(session).get(_id)
            status, round_ = book.status.value, book.current_round
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_retry_countdown(self))
    _emit(_id, status, round_)
    pipeline_draft_metadata.delay(book_id)


@celery_app.task(name="app.tasks.pipeline_draft_metadata", base=PipelineTask, bind=True, max_retries=_MAX_RETRIES)
def pipeline_draft_metadata(self, book_id: str) -> None:
    """DRAFTING_METADATA → EXPORTING; draft title/description/keywords via LLM."""
    _id = uuid.UUID(book_id)
    try:
        with get_task_session() as session:
            if _check_cancelled(session, _id):
                return
            _make_orchestrator(session).draft_metadata(_id)
            book = BookRepo(session).get(_id)
            status, round_ = book.status.value, book.current_round
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_retry_countdown(self))
    _emit(_id, status, round_)
    pipeline_export.delay(book_id)


@celery_app.task(name="app.tasks.pipeline_export", base=PipelineTask, bind=True, max_retries=_MAX_RETRIES)
def pipeline_export(self, book_id: str) -> None:
    """EXPORTING → EXPORT_READY; run compositor, write all export files."""
    _id = uuid.UUID(book_id)
    try:
        with get_task_session() as session:
            if _check_cancelled(session, _id):
                return
            _make_orchestrator(session).export_book(_id)
            book = BookRepo(session).get(_id)
            status, round_ = book.status.value, book.current_round
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_retry_countdown(self))
    _emit(_id, status, round_)
