"""Celery-приложение. Брокер — Redis (Timeweb); result backend НЕ используется (БД — правда)."""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

_settings = get_settings()

celery_app = Celery("ciw", broker=_settings.celery_broker_url, backend=None)
celery_app.conf.update(
    task_soft_time_limit=_settings.task_soft_time_limit_s,
    task_time_limit=_settings.task_time_limit_s,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
