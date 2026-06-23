"""Celery-приложение. Брокер — Redis (Timeweb); result backend НЕ используется (БД — правда)."""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

_settings = get_settings()

# include= импортит модуль задач при старте воркера (-A ...celery_app сам грузит только этот
# файл и о @celery_app.task в tasks.py не знал бы → "Received unregistered task"). Обрабатывается
# лениво на finalize, поэтому цикла deps↔tasks не создаёт.
celery_app = Celery(
    "ciw",
    broker=_settings.celery_broker_url,
    backend=None,
    include=["app.infrastructure.tasks.tasks"],
)
celery_app.conf.update(
    task_soft_time_limit=_settings.task_soft_time_limit_s,
    task_time_limit=_settings.task_time_limit_s,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Управляющий pidbox-мейлбокс (`celery inspect`/`control`) — это Redis pub/sub fanout.
    # На Redis-ACL без прав на каналы он роняет воркер в drain-цикле
    # (NoPermissionError: No permissions to access a channel). Нам он не нужен: доставка задач
    # идёт через списки (LPUSH/BRPOP), а статусы — в Postgres (result backend off). Отключаем
    # remote-control — вместе с `--without-mingle --without-gossip` (justfile) убирает все
    # fanout-подписки, и воркер работает без прав на каналы.
    worker_enable_remote_control=False,
)
