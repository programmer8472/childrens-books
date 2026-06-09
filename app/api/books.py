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
from app.tasks import pipeline_handle_revision, pipeline_run_judging, pipeline_start

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


class BookOut(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str
    current_round: int
    max_rounds: int
    score_threshold: float
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


@router.post("/books/{book_id}/approve")
def approve_book(book_id: uuid.UUID, db: Session = Depends(get_session)):
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
    repo.transition(book, BookStatus.APPROVED, actor="human")
    db.commit()
    publish_event(book_id, {"type": "status_change", "status": "APPROVED", "actor": "human"})
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
