"""Drain-to-zero эмбеддинга справочника: гоняет run_once, пока есть pending. Чист от Celery."""

from __future__ import annotations

from app.domain.ports import Embedder, EmbeddingQueueRepository
from app.services.embedding_worker import run_once

_BATCH = 100


def drain_articles(queue: EmbeddingQueueRepository, embedder: Embedder) -> int:
    """Эмбеддит все pending-статьи (включая добавленные по ходу). Возвращает число записанных."""
    total = 0
    while (written := run_once(queue, embedder, batch_size=_BATCH)) > 0:
        total += written
    return total
