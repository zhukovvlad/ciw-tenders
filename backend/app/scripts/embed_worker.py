"""Фоновый воркер эмбеддингов. Очередь = template_articles с embedding IS NULL.

Запуск: `uv run python -m app.scripts.embed_worker [--once] [--batch-size N]`.
"""

from __future__ import annotations

import argparse
import time

from app.api.deps import get_embedder
from app.infrastructure.db.embedding_queue_repository import SqlAlchemyEmbeddingQueueRepository
from app.infrastructure.db.session import SessionLocal
from app.services.embedding_worker import run_once


def main() -> None:
    parser = argparse.ArgumentParser(description="Фоновый эмбеддинг справочника СМР")
    parser.add_argument("--once", action="store_true", help="один проход и выход")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--sleep", type=float, default=5.0, help="пауза между проходами, сек")
    args = parser.parse_args()

    embedder = get_embedder()
    while True:
        session = SessionLocal()
        try:
            queue = SqlAlchemyEmbeddingQueueRepository(session)
            written = run_once(queue, embedder, batch_size=args.batch_size)
        finally:
            session.close()

        if args.once:
            print(f"Записано векторов: {written}")
            return
        if written == 0:
            time.sleep(args.sleep)


if __name__ == "__main__":
    main()
