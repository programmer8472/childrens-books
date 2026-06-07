"""FastAPI app. Unit 0: just /health and a worker round-trip probe."""
from fastapi import FastAPI

from app.celery_app import celery_app
from app.tasks import ping

app = FastAPI(title="AI Book Publishing Platform", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/health/worker")
def health_worker() -> dict[str, str]:
    """Enqueue the trivial task and block briefly for its result.

    Diagnostic only — real command endpoints (Unit 5) never block on workers.
    """
    result = ping.delay()
    return {"task_id": result.id, "result": result.get(timeout=10)}


__all__ = ["app", "celery_app"]
