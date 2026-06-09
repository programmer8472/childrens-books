"""Pipeline event publishing via Redis pub/sub.

Workers call publish_event() after each significant step.
The WebSocket endpoint subscribes and forwards to the browser.
"""
import json
import uuid
from datetime import datetime, timezone

import redis as _redis

from app.config import get_settings

_client: _redis.Redis | None = None


def _get_client() -> _redis.Redis:
    global _client
    if _client is None:
        _client = _redis.from_url(get_settings().redis_url)
    return _client


def channel_for(book_id: uuid.UUID) -> str:
    return f"book:{book_id}:events"


def publish_event(book_id: uuid.UUID, event: dict) -> None:
    """Publish a pipeline event to the book's Redis channel.

    Failures are silently swallowed — event delivery must not break the pipeline.
    """
    try:
        payload = json.dumps(
            {"book_id": str(book_id), "timestamp": datetime.now(timezone.utc).isoformat(), **event}
        )
        _get_client().publish(channel_for(book_id), payload)
    except Exception:
        pass
