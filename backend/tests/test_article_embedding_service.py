from __future__ import annotations

from app.domain.entities import PendingEmbedding
from app.services.article_embedding_service import drain_articles


class _Queue:
    def __init__(self, pending_rounds: list[list[PendingEmbedding]]) -> None:
        self._rounds = pending_rounds
        self.saved: list[int] = []

    def fetch_pending(self, limit: int):
        return self._rounds.pop(0) if self._rounds else []

    def save_embedding(self, article_id, embedding_input, vector) -> bool:
        self.saved.append(article_id)
        return True


class _Embedder:
    def embed(self, text):
        return [0.1]

    def embed_batch(self, texts):
        return [[0.1] for _ in texts]


def test_drain_to_zero_processes_all_rounds() -> None:
    q = _Queue([[PendingEmbedding(1, "a"), PendingEmbedding(2, "b")], [PendingEmbedding(3, "c")]])
    written = drain_articles(q, _Embedder())
    assert written == 3 and q.saved == [1, 2, 3]  # докрутился до нуля (включая «доехавшие» позже)
