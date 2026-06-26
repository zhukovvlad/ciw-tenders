"""Celery-приложение. Брокер — Redis (Timeweb); result backend НЕ используется (БД — правда)."""

from __future__ import annotations

from celery import Celery
from celery.signals import setup_logging as celery_setup_logging
from celery.signals import task_postrun, task_prerun

from app.core.config import get_settings
from app.core.logging_config import (
    bind_request_id,
    bind_task_id,
    reset_correlation,
    setup_logging,
)

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
    worker_hijack_root_logger=False,  # иначе Celery переопределит наш форматтер/фильтр
)


@celery_setup_logging.connect
def _on_setup_logging(**_kwargs) -> None:
    # Перехватываем настройку логирования у Celery → наш setup_logging() (с фильтром req/task).
    setup_logging()


@task_prerun.connect
def _on_task_prerun(task_id=None, task=None, **_kwargs) -> None:
    bind_task_id(task_id)
    # ВНИМАНИЕ (open item, см. spec §2): точный аксессор кастомного заголовка версионно-зависим
    # в celery 5.6.3. Отказ тихий — request_id останется None. Проверить на реальном Redis (Step 6).
    request_id = getattr(task.request, "request_id", None) if task is not None else None
    bind_request_id(request_id)


@task_postrun.connect
def _on_task_postrun(**_kwargs) -> None:
    reset_correlation()  # ОБЯЗАТЕЛЬНО: solo-pool переиспользует процесс → иначе id протечёт
