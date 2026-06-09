"""Celery tasks.

Each pipeline task does exactly one step, commits, then enqueues the next.
Tasks are idempotent: re-running a task for the same (book_id, round, method)
is safe — the orchestrator skips work already done.
"""
import uuid

from app.celery_app import celery_app
from app.config import get_settings
from app.db.repos import BookRepo, ImageRepo, JudgementRepo, StoryVersionRepo
from app.db.session import get_task_session
from app.events import publish_event
from app.orchestrator import Orchestrator
from app.providers.factory import get_image_provider, get_llm_provider
from app.storage.local import LocalStorage


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

@celery_app.task(name="app.tasks.pipeline_start", bind=True, max_retries=3)
def pipeline_start(self, book_id: str) -> None:
    """Kick off a book: DRAFT_BRIEF → OUTLINING → WRITING → JUDGING."""
    _id = uuid.UUID(book_id)
    try:
        with get_task_session() as session:
            _make_orchestrator(session).start(_id)
            book = BookRepo(session).get(_id)
            status, round_ = book.status.value, book.current_round
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)
    _emit(_id, status, round_)
    pipeline_run_judging.delay(book_id)


@celery_app.task(name="app.tasks.pipeline_run_judging", bind=True, max_retries=3)
def pipeline_run_judging(self, book_id: str) -> None:
    """Judge current-round versions; advance to AWAITING_APPROVAL, REVISION, or RETIRED."""
    _id = uuid.UUID(book_id)
    try:
        with get_task_session() as session:
            orch = _make_orchestrator(session)
            orch.run_judging(_id)
            book = BookRepo(session).get(_id)
            status, round_ = book.status.value, book.current_round
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)
    _emit(_id, status, round_)
    if status == "REVISION":
        pipeline_handle_revision.delay(book_id)


@celery_app.task(name="app.tasks.pipeline_handle_revision", bind=True, max_retries=3)
def pipeline_handle_revision(self, book_id: str) -> None:
    """REVISION → WRITING; increment round; run next writing round."""
    _id = uuid.UUID(book_id)
    try:
        with get_task_session() as session:
            _make_orchestrator(session).handle_revision(_id)
            book = BookRepo(session).get(_id)
            status, round_ = book.status.value, book.current_round
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)
    _emit(_id, status, round_)
    pipeline_run_judging.delay(book_id)


# ---------------------------------------------------------------------------
# Pipeline — post-approval stages
# ---------------------------------------------------------------------------

@celery_app.task(name="app.tasks.pipeline_generate_images", bind=True, max_retries=3)
def pipeline_generate_images(self, book_id: str) -> None:
    """APPROVED → GENERATING_IMAGES; generate 12 interior scene images."""
    _id = uuid.UUID(book_id)
    try:
        with get_task_session() as session:
            def _cb(current, total):
                _emit_progress(_id, current, total, "GENERATING_IMAGES")

            _make_orchestrator(session).generate_images(_id, event_cb=_cb)
            book = BookRepo(session).get(_id)
            status, round_ = book.status.value, book.current_round
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)
    _emit(_id, status, round_)
    pipeline_generate_cover.delay(book_id)


@celery_app.task(name="app.tasks.pipeline_generate_cover", bind=True, max_retries=3)
def pipeline_generate_cover(self, book_id: str) -> None:
    """GENERATING_COVER → DRAFTING_METADATA; generate cover image."""
    _id = uuid.UUID(book_id)
    try:
        with get_task_session() as session:
            _make_orchestrator(session).generate_cover(_id)
            book = BookRepo(session).get(_id)
            status, round_ = book.status.value, book.current_round
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)
    _emit(_id, status, round_)
    pipeline_draft_metadata.delay(book_id)


@celery_app.task(name="app.tasks.pipeline_draft_metadata", bind=True, max_retries=3)
def pipeline_draft_metadata(self, book_id: str) -> None:
    """DRAFTING_METADATA → EXPORTING; draft title/description/keywords via LLM."""
    _id = uuid.UUID(book_id)
    try:
        with get_task_session() as session:
            _make_orchestrator(session).draft_metadata(_id)
            book = BookRepo(session).get(_id)
            status, round_ = book.status.value, book.current_round
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)
    _emit(_id, status, round_)
    pipeline_export.delay(book_id)


@celery_app.task(name="app.tasks.pipeline_export", bind=True, max_retries=3)
def pipeline_export(self, book_id: str) -> None:
    """EXPORTING → EXPORT_READY; run compositor, write all export files."""
    _id = uuid.UUID(book_id)
    try:
        with get_task_session() as session:
            _make_orchestrator(session).export_book(_id)
            book = BookRepo(session).get(_id)
            status, round_ = book.status.value, book.current_round
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)
    _emit(_id, status, round_)
