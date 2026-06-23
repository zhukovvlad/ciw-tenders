"""Тонкие Celery-обёртки: ВЫДЕЛЕННЫЙ коннект → сессия на нём → сервис → коммиты. Логика брокера ТУТ.

КРИТИЧНО (advisory-lock): session-level advisory-lock живёт на backend-коннекте и переживает
COMMIT, НО `SessionLocal()` привязан к engine → `commit()` возвращает коннект в пул, и следующая
операция берёт ДРУГОЙ коннект (лок утекает, эксклюзивность теряется на prefork concurrency>1).
Поэтому задача открывает ОДИН коннект `engine.connect()` на всё время и строит сессию
`SessionLocal(bind=conn)` — при внешнем bind `commit()` НЕ возвращает коннект в пул, все операции
и лок остаются на нём. release_*_lock выполняется в сервисе/обёртке ДО `conn.close()`. Краш/SIGKILL
(тайм-лимит) → коннект рвётся → Postgres сам отпускает лок (детектор живости).
"""

from __future__ import annotations

from app.core.config import get_settings
from app.domain.errors import DictionaryNotReadyError
from app.infrastructure.db.embedding_queue_repository import SqlAlchemyEmbeddingQueueRepository
from app.infrastructure.db.session import SessionLocal, engine
from app.infrastructure.tasks.celery_app import celery_app
from app.services.article_embedding_service import drain_articles

_settings = get_settings()


def run_match(service, estimate_id: int, *, is_final: bool) -> None:
    """Чистая логика gate-retry без Celery: gate-не-готов и попытки исчерпаны → mark_blocked;
    иначе пробрасывает DictionaryNotReadyError (обёртка решает self.retry)."""
    try:
        service.match_estimate(estimate_id)
    except DictionaryNotReadyError as exc:
        if is_final:
            service.mark_blocked(estimate_id, detail=f"timeout ждали справочник: {exc}")
            return
        raise


@celery_app.task(bind=True, max_retries=_settings.gate_retry_max)
def match_estimate_task(self, estimate_id: int) -> None:
    # ленивый импорт — нет цикла deps↔tasks
    from app.api.deps import build_estimate_matching_service  # noqa: I001

    conn = engine.connect()                       # пиннутый коннект на всю задачу
    try:
        session = SessionLocal(bind=conn)         # bind=conn → commit() не вернёт коннект в пул
        try:
            service = build_estimate_matching_service(session)
            is_final = self.request.retries >= self.max_retries
            try:
                run_match(service, estimate_id, is_final=is_final)
            except DictionaryNotReadyError as exc:
                raise self.retry(exc=exc, countdown=_settings.gate_retry_backoff_s) from exc
        finally:
            session.close()                       # внешний conn НЕ закрывает
    finally:
        conn.close()                              # лок уже снят в сервисе → коннект в пул чистым


@celery_app.task
def embed_articles_task() -> None:
    from app.api.deps import get_embedder  # ленивый импорт

    conn = engine.connect()                 # пиннутый коннект (singleton-лок переживёт коммиты)
    try:
        session = SessionLocal(bind=conn)
        try:
            queue = SqlAlchemyEmbeddingQueueRepository(session)
            if not queue.try_embed_lock():
                return  # singleton → no-op
            try:
                drain_articles(queue, get_embedder())
            finally:
                queue.release_embed_lock()
        finally:
            session.close()
    finally:
        conn.close()
