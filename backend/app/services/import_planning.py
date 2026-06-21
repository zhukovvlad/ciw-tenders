"""Чистая логика дельты импорта: insert/update/delete + инвалидация + порог force.

Файл трактуется как полное желаемое состояние (full-replace-by-diff). Удаление защищено
требованием force при сносе корня или большой доли строк (см. requires_force).
"""

from __future__ import annotations

from app.domain.entities import (
    ExistingArticle,
    ImportPlan,
    PlannedInsert,
    PlannedUpdate,
)
from app.services.template_parser import ParsedTemplateRow


def compute_plan(
    parsed: list[ParsedTemplateRow], existing: list[ExistingArticle]
) -> ImportPlan:
    existing_by_code = {e.article_code: e for e in existing}
    parsed_codes = {r.article_code for r in parsed}

    inserts: list[PlannedInsert] = []
    updates: list[PlannedUpdate] = []
    unchanged = 0

    for row in parsed:
        current = existing_by_code.get(row.article_code)
        if current is None:
            inserts.append(
                PlannedInsert(
                    article_code=row.article_code,
                    name=row.name,
                    parent_code=row.parent_code,
                    embedding_input=row.embedding_input,
                )
            )
            continue
        if current.embedding_input == row.embedding_input:
            unchanged += 1
            continue
        # invalidate_embedding сейчас всегда True по построению: в updates попадают только
        # строки с изменившимся embedding_input. Поле явное, чтобы решение об инвалидации
        # жило в compute_plan (политика), а apply_plan лишь исполнял намерение, не выводя
        # политику заново. Инвариант закреплён test_update_invalidates_when_embedding_input_changed.
        updates.append(
            PlannedUpdate(
                id=current.id,
                article_code=row.article_code,
                name=row.name,
                parent_code=row.parent_code,
                embedding_input=row.embedding_input,
                invalidate_embedding=True,
            )
        )

    deletions = [e for e in existing if e.article_code not in parsed_codes]
    return ImportPlan(
        inserts=inserts,
        updates=updates,
        delete_ids=[e.id for e in deletions],
        delete_codes=[e.article_code for e in deletions],
        unchanged=unchanged,
    )


def requires_force(
    plan: ImportPlan, existing_total: int, *, fraction_limit: float = 0.20
) -> bool:
    if existing_total == 0:
        return False
    roots_deleted = sum(1 for code in plan.delete_codes if "." not in code)
    if roots_deleted >= 1:
        return True
    return len(plan.delete_ids) > fraction_limit * existing_total
