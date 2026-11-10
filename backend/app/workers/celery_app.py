from celery import Celery

from app.config import settings

celery_app = Celery(
    "kb_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.document_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    task_track_started=True,
    task_time_limit=3600,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
)
