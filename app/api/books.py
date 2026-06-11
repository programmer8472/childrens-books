"""Book endpoints: CRUD, pipeline commands, and WebSocket event streaming."""
import asyncio
import contextlib
import uuid
from datetime import datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db.enums import BookStatus
from app.db.models import StoryVersion
from app.db.repos import BookRepo, StoryVersionRepo
from app.db.session import get_session
from app.events import channel_for, publish_event
from app.storage.local import LocalStorage
from app.tasks import (
    pipeline_generate_images,
    pipeline_handle_revision,
    pipeline_rejudge_shortlist,
    pipeline_run_judging,
    pipeline_start,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class CreateBookIn(BaseModel):
    brief: dict
    title: str | None = None
    max_rounds: int = 5
    score_threshold: float = 7.5


class RejectIn(BaseModel):
    note: str | None = None


class ApproveIn(BaseModel):
    story_version_id: uuid.UUID | None = None


class ShortlistIn(BaseModel):
    story_version_ids: list[uuid.UUID]


class BookOut(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str
    current_round: int
    max_rounds: int
    score_threshold: float
    cancel_requested: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JudgementOut(BaseModel):
    id: uuid.UUID
    story_version_id: uuid.UUID
    round: int
    emotional_authenticity: float
    representation_quality: float
    pacing: float
    age_fit: float
    uniqueness: float
    weighted_total: float
    passed: bool
    critique: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VersionOut(BaseModel):
    id: uuid.UUID
    round: int
    method: str
    content: str
    shortlisted: bool
    judgements: list[JudgementOut]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/books", response_model=BookOut, status_code=201)
def create_book(body: CreateBookIn, db: Session = Depends(get_session)):
    book = BookRepo(db).create(
        body.brief,
        title=body.title,
        max_rounds=body.max_rounds,
        score_threshold=body.score_threshold,
    )
    db.commit()
    pipeline_start.delay(str(book.id))
    publish_event(book.id, {"type": "pipeline_queued", "actor": "api"})
    return book


@router.get("/books", response_model=list[BookOut])
def list_books(db: Session = Depends(get_session)):
    return BookRepo(db).list_all()


@router.get("/books/{book_id}", response_model=BookOut)
def get_book(book_id: uuid.UUID, db: Session = Depends(get_session)):
    try:
        return BookRepo(db).get(book_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Book not found")


@router.get("/books/{book_id}/versions", response_model=list[VersionOut])
def get_versions(book_id: uuid.UUID, db: Session = Depends(get_session)):
    try:
        BookRepo(db).get(book_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Book not found")
    stmt = (
        select(StoryVersion)
        .where(StoryVersion.book_id == book_id)
        .options(selectinload(StoryVersion.judgements))
        .order_by(StoryVersion.created_at)
    )
    return list(db.scalars(stmt))


@router.post("/books/{book_id}/shortlist")
def shortlist_book(book_id: uuid.UUID, body: ShortlistIn, db: Session = Depends(get_session)):
    """Phase 1 → Phase 2: submit selected versions for re-judging."""
    repo = BookRepo(db)
    try:
        book = repo.get(book_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.status != BookStatus.AWAITING_SHORTLIST:
        raise HTTPException(
            status_code=400,
            detail=f"Book is {book.status.value}; expected AWAITING_SHORTLIST",
        )
    if not body.story_version_ids:
        raise HTTPException(status_code=400, detail="story_version_ids must not be empty")
    db.commit()
    pipeline_rejudge_shortlist.delay(str(book_id), [str(v) for v in body.story_version_ids])
    publish_event(book_id, {"type": "shortlist_submitted", "actor": "human"})
    return {"ok": True, "status": "SHORTLIST_JUDGING"}


@router.post("/books/{book_id}/approve")
def approve_book(
    book_id: uuid.UUID,
    body: ApproveIn = Body(default=ApproveIn()),
    db: Session = Depends(get_session),
):
    """Phase 3 → APPROVED: human selects a story version and approves.

    For books in AWAITING_FINAL_APPROVAL (new flow), story_version_id is required.
    For books in AWAITING_APPROVAL (legacy gate), story_version_id is optional.
    """
    repo = BookRepo(db)
    try:
        book = repo.get(book_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Book not found")

    _allowed = {BookStatus.AWAITING_FINAL_APPROVAL, BookStatus.AWAITING_APPROVAL}
    if book.status not in _allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Book is {book.status.value}; expected AWAITING_FINAL_APPROVAL or AWAITING_APPROVAL",
        )

    if book.status == BookStatus.AWAITING_FINAL_APPROVAL:
        if not body.story_version_id:
            raise HTTPException(
                status_code=400,
                detail="story_version_id is required when approving from AWAITING_FINAL_APPROVAL",
            )
        repo.set_approved_version(book, body.story_version_id)

    repo.transition(book, BookStatus.APPROVED, actor="human")
    db.commit()
    publish_event(book_id, {"type": "status_change", "status": "APPROVED", "actor": "human"})
    pipeline_generate_images.delay(str(book_id))
    return {"ok": True, "status": "APPROVED"}


@router.post("/books/{book_id}/reject")
def reject_book(
    book_id: uuid.UUID,
    body: RejectIn = Body(default=RejectIn()),
    db: Session = Depends(get_session),
):
    repo = BookRepo(db)
    try:
        book = repo.get(book_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.status != BookStatus.AWAITING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail=f"Book is {book.status.value}; expected AWAITING_APPROVAL",
        )
    repo.transition(book, BookStatus.REVISION, actor="human", note=body.note)
    db.commit()
    publish_event(book_id, {"type": "status_change", "status": "REVISION", "actor": "human"})
    pipeline_handle_revision.delay(str(book_id))
    return {"ok": True, "status": "REVISION"}


@router.post("/books/{book_id}/retry")
def retry_book(book_id: uuid.UUID, db: Session = Depends(get_session)):
    try:
        book = BookRepo(db).get(book_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.status == BookStatus.JUDGING:
        pipeline_run_judging.delay(str(book_id))
        return {"ok": True, "task": "pipeline_run_judging"}
    if book.status == BookStatus.REVISION:
        pipeline_handle_revision.delay(str(book_id))
        return {"ok": True, "task": "pipeline_handle_revision"}
    raise HTTPException(
        status_code=400,
        detail=f"Cannot retry from {book.status.value}; retryable states: JUDGING, REVISION",
    )


# Human gates have no pending automated task, so a cancel there must transition
# immediately. Running/queued stages have a task in flight whose boundary guard
# will pick up the flag. Terminal states can't be cancelled.
_HUMAN_GATES = frozenset({
    BookStatus.AWAITING_SHORTLIST,
    BookStatus.AWAITING_FINAL_APPROVAL,
    BookStatus.AWAITING_APPROVAL,
})
_UNCANCELLABLE = frozenset({
    BookStatus.EXPORT_READY,
    BookStatus.DONE,
    BookStatus.RETIRED,
    BookStatus.CANCELLED,
})


@router.post("/books/{book_id}/cancel")
def cancel_book(book_id: uuid.UUID, db: Session = Depends(get_session)):
    """Human stop request. Cancels gate states immediately; flags running ones."""
    repo = BookRepo(db)
    try:
        book = repo.get(book_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.status in _UNCANCELLABLE:
        raise HTTPException(status_code=400, detail=f"Book is {book.status.value}; cannot cancel")

    repo.request_cancel(book)
    if book.status in _HUMAN_GATES:
        repo.cancel(book, note="Cancelled by human")
        db.commit()
        publish_event(book_id, {"type": "cancelled", "status": "CANCELLED", "actor": "human"})
        return {"ok": True, "status": "CANCELLED"}

    db.commit()
    publish_event(book_id, {"type": "cancel_requested", "actor": "human"})
    return {"ok": True, "status": book.status.value, "cancelling": True}


# ---------------------------------------------------------------------------
# Metadata: GET + PUT (human-editable before export)
# ---------------------------------------------------------------------------


class RewriteIn(BaseModel):
    paragraph_text: str
    instruction: str


@router.post("/books/{book_id}/paragraphs/rewrite")
def rewrite_paragraph(book_id: uuid.UUID, body: RewriteIn, db: Session = Depends(get_session)):
    """Inline editor: rewrite a paragraph with a natural-language instruction."""
    try:
        BookRepo(db).get(book_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Book not found")

    from app.providers.factory import get_llm_provider

    provider = get_llm_provider()
    system = (
        "You are a children's book editor. Rewrite the given paragraph following the "
        "user's instruction. Keep the same reading level, character names, and story "
        "context. Return only the rewritten paragraph, nothing else."
    )
    messages = [
        {
            "role": "user",
            "content": f"Paragraph:\n{body.paragraph_text}\n\nInstruction: {body.instruction}",
        }
    ]
    response = provider.generate(system, messages)
    return {"original": body.paragraph_text, "rewritten": response.content.strip()}


class MetadataIn(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    author: str | None = None
    description: str | None = None
    keywords: list[str] | None = None
    age_range: str | None = None
    series_name: str | None = None


@router.get("/books/{book_id}/metadata")
def get_metadata(book_id: uuid.UUID, db: Session = Depends(get_session)):
    try:
        book = BookRepo(db).get(book_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Book not found")
    return book.book_metadata or {}


@router.put("/books/{book_id}/metadata")
def update_metadata(book_id: uuid.UUID, body: MetadataIn, db: Session = Depends(get_session)):
    repo = BookRepo(db)
    try:
        book = repo.get(book_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Book not found")
    current = dict(book.book_metadata or {})
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    current.update(updates)
    repo.save_metadata(book, current)
    db.commit()
    return current


# ---------------------------------------------------------------------------
# Export: GET manifest and download individual files
# ---------------------------------------------------------------------------


@router.get("/books/{book_id}/export")
def get_export_manifest(book_id: uuid.UUID, db: Session = Depends(get_session)):
    try:
        book = BookRepo(db).get(book_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.status.value not in ("EXPORT_READY", "DONE"):
        raise HTTPException(status_code=400, detail=f"Book is {book.status.value}; not yet EXPORT_READY")
    return book.export_manifest or {}


@router.get("/books/{book_id}/previews")
def get_previews(book_id: uuid.UUID, db: Session = Depends(get_session)):
    """Return the ordered preview-page count and the preflight QA report.

    Available whenever composition has run (EXPORT_READY, DONE, or a book
    retired by a failed preflight), so the human can visually inspect the
    rendered pages and see why a book was blocked.
    """
    try:
        book = BookRepo(db).get(book_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Book not found")
    manifest = book.export_manifest or {}
    previews = manifest.get("previews") or []
    return {
        "count": len(previews),
        "preflight": manifest.get("preflight"),
    }


@router.get("/books/{book_id}/previews/{index}")
def get_preview_page(book_id: uuid.UUID, index: int, db: Session = Depends(get_session)):
    """Serve a single rendered preview page (PNG) by 0-based index."""
    from fastapi.responses import Response

    try:
        book = BookRepo(db).get(book_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Book not found")
    previews = (book.export_manifest or {}).get("previews") or []
    if not (0 <= index < len(previews)):
        raise HTTPException(status_code=404, detail="Preview page not found")
    storage = LocalStorage(get_settings().storage_local_root)
    try:
        data = storage.get(previews[index])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Preview file not found in storage")
    return Response(content=data, media_type="image/png")


@router.get("/books/{book_id}/export/{artifact}")
def download_export(book_id: uuid.UUID, artifact: str, db: Session = Depends(get_session)):
    """Download a single export artifact by name (interior_pdf, cover_pdf, word, markdown, text)."""
    from fastapi.responses import Response

    try:
        book = BookRepo(db).get(book_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Book not found")
    manifest = book.export_manifest or {}
    if artifact not in manifest:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact}' not in export manifest")
    storage_key = manifest[artifact]
    storage = LocalStorage(get_settings().storage_local_root)
    try:
        data = storage.get(storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact file not found in storage")

    _content_types = {
        "interior_pdf": "application/pdf",
        "cover_pdf": "application/pdf",
        "word": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "markdown": "text/markdown",
        "text": "text/plain",
    }
    content_type = _content_types.get(artifact, "application/octet-stream")
    filename = storage_key.rsplit("/", 1)[-1]
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# WebSocket: live event stream for a single book
# ---------------------------------------------------------------------------


@router.websocket("/books/{book_id}/stream")
async def book_stream(websocket: WebSocket, book_id: uuid.UUID):
    """Subscribe to pipeline events for a book and forward them to the client."""
    await websocket.accept()
    settings = get_settings()
    r = aioredis.from_url(settings.redis_url)
    pubsub = r.pubsub()
    channel = channel_for(book_id)
    await pubsub.subscribe(channel)

    async def _forward() -> None:
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    await websocket.send_text(
                        data.decode() if isinstance(data, bytes) else data
                    )
        except Exception:
            pass

    forward_task = asyncio.create_task(_forward())
    try:
        while True:
            await websocket.receive()  # blocks until client sends or disconnects
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        forward_task.cancel()
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel)
        with contextlib.suppress(Exception):
            await r.aclose()
