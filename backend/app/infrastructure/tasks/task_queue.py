"""CeleryTaskQueue — адаптер порта TaskQueue. enqueue → .delay(), возвращает None."""

from __future__ import annotations

from app.domain.ports import TaskQueue
from app.infrastructure.tasks.tasks import embed_articles_task, match_estimate_task


class CeleryTaskQueue(TaskQueue):
    def enqueue_match(self, estimate_id: int) -> None:
        match_estimate_task.delay(estimate_id)

    def enqueue_articles_embed(self) -> None:
        embed_articles_task.delay()
