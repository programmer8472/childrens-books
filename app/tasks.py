"""Celery tasks.

Each pipeline task does exactly one step, commits, then enqueues the next.
Tasks are idempotent: re-running a task for the same (book_id, round, method)
is safe — the orchestrator skips work already done.
"""
import uuid

from app.celery_app import celery_app
from app.db.repos import BookRepo, JudgementRepo, StoryVersionRepo
from app.db.session import get_task_session
from app.orchestrator import Orchestrator
from app.providers.factory import get_image_provider, get_llm_provider


def _make_orchestrator(session):
    return Orchestrator(
        book_repo=BookRepo(session),
        version_repo=StoryVersionRepo(session),
        judgement_repo=JudgementRepo(session),
        llm=get_llm_provider(),
        image=get_image_provider(),
    )


# ---------------------------------------------------------------------------
# Diagnostic
# ---------------------------------------------------------------------------

@celery_app.task(name="app.tasks.ping")
def ping() -> str:
    """Trivial round-trip check: enqueue this, get 'pong' back from a worker."""
    return "pong"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

@celery_app.task(name="app.tasks.pipeline_start", bind=True, max_retries=3)
def pipeline_start(self, book_id: str) -> None:
    """Kick off a book: DRAFT_BRIEF → OUTLINING → WRITING → JUDGING."""
    try:
        with get_task_session() as session:
            _make_orchestrator(session).start(uuid.UUID(book_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)
    pipeline_run_judging.delay(book_id)


@celery_app.task(name="app.tasks.pipeline_run_judging", bind=True, max_retries=3)
def pipeline_run_judging(self, book_id: str) -> None:
    """Judge current-round versions; advance to AWAITING_APPROVAL, REVISION, or RETIRED."""
    try:
        with get_task_session() as session:
            orch = _make_orchestrator(session)
            orch.run_judging(uuid.UUID(book_id))
            book = BookRepo(session).get(uuid.UUID(book_id))
            next_status = book.status.value
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)

    if next_status == "REVISION":
        pipeline_handle_revision.delay(book_id)


@celery_app.task(name="app.tasks.pipeline_handle_revision", bind=True, max_retries=3)
def pipeline_handle_revision(self, book_id: str) -> None:
    """REVISION → WRITING; increment round; run next writing round."""
    try:
        with get_task_session() as session:
            _make_orchestrator(session).handle_revision(uuid.UUID(book_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)
    pipeline_run_judging.delay(book_id)
