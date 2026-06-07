"""Celery application. Workers run slow work off the request path."""
from celery import Celery

from app.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "childrens_books",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
