"""CeleryTaskQueue — адаптер порта TaskQueue. enqueue → .delay(), возвращает None."""

from __future__ import annotations

from app.core.logging_config import get_request_id
from app.domain.ports import TaskQueue
from app.infrastructure.tasks.tasks import embed_articles_task, match_estimate_task


class CeleryTaskQueue(TaskQueue):
    def enqueue_match(self, estimate_id: int) -> None:
        # request_id едет в заголовке сообщения → воркер восстановит корреляцию (task_prerun).
        match_estimate_task.apply_async(
            (estimate_id,), headers={"request_id": get_request_id()}
        )

    def enqueue_articles_embed(self) -> None:
        # fan-in drain (тянет pending из многих запросов) — НАМЕРЕННО вне request-корреляции,
        # коррелируется только по task_id.
        embed_articles_task.delay()
