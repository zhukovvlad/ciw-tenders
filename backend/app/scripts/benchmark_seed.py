"""Сид бенчмарка из размеченной сметы (xlsx → БД). Разовая админ-операция.

Запуск: uv run python -m app.scripts.benchmark_seed --gold "<path>" [--name <name>] [--yes]
`no_article`-узлы печатаются громко и требуют подтверждения (или флаг --yes).
"""

from __future__ import annotations

import argparse
import logging
import os

from app.core.logging_config import setup_logging
from app.domain.benchmark import BenchmarkKind
from app.infrastructure.benchmark_xlsx import read_benchmark_nodes
from app.infrastructure.db.benchmark_repository import SqlAlchemyBenchmarkRepository
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()  # конвенция CLI-скриптов: логи до Settings-валидации
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", required=True, help="путь к размеченному xlsx")
    parser.add_argument("--name", default=None, help="имя бенчмарка (по умолчанию — basename)")
    parser.add_argument("--yes", action="store_true", help="не спрашивать подтверждение no_article")
    args = parser.parse_args()

    nodes = read_benchmark_nodes(args.gold)
    name = args.name or os.path.splitext(os.path.basename(args.gold))[0]

    kinds = dict.fromkeys(
        (BenchmarkKind.MATCHABLE, BenchmarkKind.STRUCTURAL, BenchmarkKind.NO_ARTICLE), 0
    )
    for n in nodes:
        kinds[BenchmarkKind(n.expected_kind)] += 1
    print(
        f"Узлов: {len(nodes)} | matchable={kinds[BenchmarkKind.MATCHABLE]} "
        f"structural={kinds[BenchmarkKind.STRUCTURAL]} no_article={kinds[BenchmarkKind.NO_ARTICLE]}"
    )

    no_art = [n for n in nodes if n.expected_kind == BenchmarkKind.NO_ARTICLE.value]
    if no_art:
        print("\n=== ПОДТВЕРДИТЕ no_article (работа без статьи в справочнике): ===")
        for n in no_art:
            print(f"  {n.code} | {n.name}")
        if not args.yes:
            answer = input("\nВсе перечисленные узлы действительно без статьи? [y/N]: ")
            answer = answer.strip().lower()
            if answer != "y":
                raise SystemExit("Отменено. Поправьте разметку в xlsx и повторите.")

    session = SessionLocal()
    try:
        repo = SqlAlchemyBenchmarkRepository(session)
        if repo.get_by_name(name) is not None:
            raise SystemExit(f"Бенчмарк '{name}' уже существует. Удалите его или задайте --name.")
        benchmark_id = repo.create(name, nodes)
        # Статус-сообщение → логгер (как create_admin); сводка/подтверждение выше —
        # print/input (интерактивный вывод программы для решения оператора).
        logger.info("Создан бенчмарк '%s' (id=%s), узлов: %d.", name, benchmark_id, len(nodes))
    finally:
        session.close()


if __name__ == "__main__":
    main()
