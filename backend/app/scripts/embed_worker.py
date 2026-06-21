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


def _positive_int(value: str) -> int:
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError("должно быть > 0")
    return ivalue


def _non_negative_float(value: str) -> float:
    fvalue = float(value)
    if fvalue < 0:
        raise argparse.ArgumentTypeError("должно быть >= 0")
    return fvalue


def main() -> None:
    parser = argparse.ArgumentParser(description="Фоновый эмбеддинг справочника СМР")
    parser.add_argument("--once", action="store_true", help="один проход и выход")
    parser.add_argument("--batch-size", type=_positive_int, default=100)
    parser.add_argument(
        "--sleep", type=_non_negative_float, default=5.0, help="пауза между проходами, сек"
    )
    args = parser.parse_args()

    embedder = get_embedder()
    while True:
        session = SessionLocal()
        try:
            queue = SqlAlchemyEmbeddingQueueRepository(session)
            written = run_once(queue, embedder, batch_size=args.batch_size)
        except Exception as exc:  # noqa: BLE001 — демон должен пережить транзиентный сбой
            session.rollback()
            if args.once:
                raise
            print(f"Ошибка прохода, повтор через {args.sleep}с: {exc}")
            time.sleep(args.sleep)
            continue
        finally:
            session.close()

        if args.once:
            print(f"Записано векторов: {written}")
            return
        if written == 0:
            time.sleep(args.sleep)


if __name__ == "__main__":
    main()
