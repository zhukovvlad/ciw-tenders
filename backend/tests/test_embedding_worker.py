from __future__ import annotations

from app.domain.entities import PendingEmbedding
from app.domain.ports import EmbeddingQueueRepository
from app.services.embedding_worker import run_once
from tests.fakes import FakeEmbedder


class _Queue(EmbeddingQueueRepository):
    def __init__(self, pending: list[PendingEmbedding]) -> None:
        self._pending = list(pending)
        self.saved: dict[int, list[float]] = {}
        self.stale_inputs: set[int] = set()  # id, для которых CAS не сматчится

    def fetch_pending(self, limit: int) -> list[PendingEmbedding]:
        batch = self._pending[:limit]
        self._pending = self._pending[limit:]
        return batch

    def save_embedding(self, article_id: int, embedding_input: str, vector: list[float]) -> bool:
        if article_id in self.stale_inputs:
            return False
        self.saved[article_id] = vector
        return True

    def try_embed_lock(self) -> bool:
        return True

    def release_embed_lock(self) -> None:
        pass


def test_run_once_embeds_pending_in_batches() -> None:
    queue = _Queue(
        [PendingEmbedding(id=1, embedding_input="a"), PendingEmbedding(id=2, embedding_input="bb")]
    )
    written = run_once(queue, FakeEmbedder(), batch_size=10)
    assert written == 2
    assert set(queue.saved) == {1, 2}


def test_run_once_cas_skips_stale_row() -> None:
    queue = _Queue(
        [PendingEmbedding(id=1, embedding_input="a"), PendingEmbedding(id=2, embedding_input="b")]
    )
    queue.stale_inputs.add(2)  # импорт сменил текст -> CAS не сматчится
    written = run_once(queue, FakeEmbedder(), batch_size=10)
    assert written == 1
    assert 1 in queue.saved
    assert 2 not in queue.saved


def test_run_once_returns_zero_when_empty() -> None:
    assert run_once(_Queue([]), FakeEmbedder(), batch_size=10) == 0
