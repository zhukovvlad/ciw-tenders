from __future__ import annotations

from collections.abc import Sequence

from app.domain.classification import (
    WorkClass,
    build_embedding_input,
    resolve_ancestor_indices,
)
from app.domain.entities import StoredEstimateRow

# ПРЕДОХРАНИТЕЛЬ: этот страж верифицирует ПОЗИЦИОННЫЙ РЕЗОЛВ ПРЕДКОВ (машинерию,
# где жил баг дублей кодов) через org-free-проекцию против embedding_input,
# записанного классификатором. При изменении формата embedding_input (например,
# unit/quantity из таблицы решений роадмапа) — править ПРОЕКЦИЮ/СРАВНЕНИЕ здесь,
# а НЕ full_breadcrumbs и НЕ UI-крошку: полная цепочка для человека не обязана
# следовать за входом эмбеддера (спека этапа 2, §2a).
#
# Прокси «status == 'excluded' ⇔ предок ORG»: спасённый org-лист (ORG-класс,
# excluded=False) — всегда лист и предком не бывает. Если org-классификация
# влияла на крошку, не оставив следа в статусе, страж упадёт — это полезная
# находка о конвейере крошки, не поломка стража.
#
# Excluded-строки В инварианте сознательно (проверено на пайплайне и живых
# данных, 2026-07-03): save_node_classifications пишет embedding_input
# БЕЗУСЛОВНО всем строкам прохода, включая excluded (estimate_repository.py,
# .values(embedding_input=r.embedding_input)); в dev-БД у org-заголовков сметы
# 16 лежит org-free крошка БЕЗ собственного имени (self_class=ORG), например
# у узла «2 Этап БЦ» — «Возведение несущих конструкций здания». Вне инварианта
# только pending (сырой парсерный join до классификации).


def _row(
    id: int, code: str, name: str, depth: int, si: int, status: str, crumb: str
) -> StoredEstimateRow:
    return StoredEstimateRow(
        id=id, code=code, name=name, parent_code=None, section_type=None,
        depth=depth, embedding_input=crumb, source_index=si, status=status,
    )


def assert_breadcrumb_matches_crumb(rows: Sequence[StoredEstimateRow]) -> None:
    """Для каждой классифицированной строки: org-free-проекция полной цепочки
    == embedding_input. pending-строки вне инварианта (их крошка — сырой
    парсерный join до классификации)."""
    ordered = sorted(rows, key=lambda r: r.source_index)
    chains = resolve_ancestor_indices([r.depth for r in ordered])
    for i, row in enumerate(ordered):
        if row.status == "pending":
            continue
        ancestors = [
            (
                ordered[j].name,
                WorkClass.ORG if ordered[j].status == "excluded" else WorkClass.WORK,
            )
            for j in chains[i]
        ]
        variants = {
            build_embedding_input(row.name, ancestors, self_class=WorkClass.WORK),
            build_embedding_input(row.name, ancestors, self_class=WorkClass.ORG),
        }
        assert row.embedding_input in variants, (
            f"строка id={row.id} code={row.code}: crumb={row.embedding_input!r} "
            f"не совпал ни с одной проекцией {variants!r}"
        )


def test_plain_nested_chain() -> None:
    rows = [
        _row(1, "2", "Конструктив", 1, 0, "excluded", ""),
        _row(2, "2.4", "Подземная часть", 2, 1, "confident", "Подземная часть"),
        _row(3, "2.4.2", "Устройство приямков", 3, 2, "needs_review",
             "Подземная часть. Устройство приямков"),
    ]
    # org-предок «Конструктив» (excluded) выброшен из проекции — рукописные
    # crumb-ы отражают то, что записал бы классификатор
    assert_breadcrumb_matches_crumb(rows)


def test_rescued_org_leaf_crumb_without_own_name() -> None:
    # спасённый org-лист: kept (не excluded), но своё имя в крошке выброшено
    rows = [
        _row(1, "4", "Ж/Б конструкции", 1, 0, "confident", "Ж/Б конструкции"),
        _row(2, "4.1", "1 Этап ЖК", 2, 1, "needs_review", "Ж/Б конструкции"),
    ]
    assert_breadcrumb_matches_crumb(rows)


def test_whitespace_normalized_and_repeats_collapsed() -> None:
    rows = [
        _row(1, "1", "Кровля", 1, 0, "confident", "Кровля"),
        _row(2, "1.1", "Кровля", 2, 1, "confident", "Кровля"),  # дубль схлопнут
        _row(3, "1.1.1", "Работа  с\xa0пробелами", 3, 2, "needs_review",
             "Кровля. Работа с пробелами"),
    ]
    assert_breadcrumb_matches_crumb(rows)


def test_pending_rows_skipped() -> None:
    rows = [_row(1, "1", "Что угодно", 1, 0, "pending", "сырой парсерный вид")]
    assert_breadcrumb_matches_crumb(rows)  # не падает — pending вне инварианта


def test_guard_actually_bites() -> None:
    # самопроверка стража: сломанный crumb должен падать
    rows = [_row(1, "1", "Работа", 1, 0, "confident", "Совсем другое")]
    try:
        assert_breadcrumb_matches_crumb(rows)
    except AssertionError:
        return
    raise AssertionError("страж не заметил расхождение")
