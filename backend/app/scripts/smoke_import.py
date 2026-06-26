"""Разовый смоук: импорт реального temp/Шаблон.xlsx в БД из DATABASE_URL.

Запуск (из backend, PYTHONIOENCODING=utf-8):
    uv run python -m app.scripts.smoke_import ../temp/Шаблон.xlsx

ВАЖНО (Task 9): целься в ТЕСТОВУЮ БД. Перед прогоном переопредели DATABASE_URL
значением TEST_DATABASE_URL на время сессии (см. docs/instructions/task9-smoke-runbook.md),
убедившись, что TEST_DATABASE_URL — отдельная БД/ветка Neon, а не алиас на прод.
"""

from __future__ import annotations

import sys

from app.core.logging_config import setup_logging
from app.infrastructure.db.import_repository import SqlAlchemyArticleImportRepository
from app.infrastructure.db.session import SessionLocal
from app.services.template_ingest_service import TemplateIngestService
from app.services.template_parser import TemplateParser


def main() -> None:
    setup_logging()
    path = sys.argv[1]
    with open(path, "rb") as fh:
        content = fh.read()
    session = SessionLocal()
    try:
        service = TemplateIngestService(
            parser=TemplateParser(), repository=SqlAlchemyArticleImportRepository(session)
        )
        report = service.import_template(content, force=True)
    finally:
        session.close()
    print(report)


if __name__ == "__main__":
    main()
