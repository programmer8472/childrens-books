"""Tasks. Unit 0 ships one trivial task to prove the worker is alive."""
from app.celery_app import celery_app


@celery_app.task(name="app.tasks.ping")
def ping() -> str:
    """Trivial round-trip check: enqueue this, get 'pong' back from a worker."""
    return "pong"
