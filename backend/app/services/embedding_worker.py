"""Логика одного прохода фонового эмбеддинга. Без БД/SDK — зависит только от портов."""

from __future__ import annotations

from app.domain.ports import Embedder, EmbeddingQueueRepository


def run_once(
    queue: EmbeddingQueueRepository, embedder: Embedder, batch_size: int = 100
) -> int:
    """Векторизует одну пачку ожидающих строк. Возвращает число записанных векторов."""
    pending = queue.fetch_pending(batch_size)
    if not pending:
        return 0
    vectors = embedder.embed_batch([row.embedding_input for row in pending])
    written = 0
    for row, vector in zip(pending, vectors, strict=True):
        if queue.save_embedding(row.id, row.embedding_input, vector):
            written += 1
    return written
