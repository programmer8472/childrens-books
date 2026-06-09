"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.books import router as books_router
from app.celery_app import celery_app
from app.tasks import ping

app = FastAPI(title="AI Book Publishing Platform", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/health/worker")
def health_worker() -> dict[str, str]:
    """Enqueue the trivial task and block briefly for its result.

    Diagnostic only — real command endpoints never block on workers.
    """
    result = ping.delay()
    return {"task_id": result.id, "result": result.get(timeout=10)}


__all__ = ["app", "celery_app"]
