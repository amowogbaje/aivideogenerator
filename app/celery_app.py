# app/celery_app.py
from celery import Celery
from app.config import settings

# Initialize the Celery app and explicitly point it to your video tasks file
celery_app = Celery(
    "video_orchestrator",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    # 👇 FORCE Celery to load your specific file right on startup
    include=["app.tasks.video_tasks"] 
)

# Core worker configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)