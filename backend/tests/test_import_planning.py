from __future__ import annotations

from app.domain.entities import ExistingArticle
from app.services.import_planning import compute_plan, requires_force
from app.services.template_parser import ParsedTemplateRow


def _p(code: str, name: str, parent: str | None, ei: str) -> ParsedTemplateRow:
    return ParsedTemplateRow(article_code=code, name=name, parent_code=parent, embedding_input=ei)


def test_insert_all_when_db_empty() -> None:
    parsed = [_p("1", "Раздел", None, "Раздел")]
    plan = compute_plan(parsed, [])
    assert len(plan.inserts) == 1
    assert plan.updates == []
    assert plan.delete_ids == []
    assert plan.unchanged == 0


def test_unchanged_keeps_embedding() -> None:
    parsed = [_p("1", "Раздел", None, "Раздел")]
    existing = [ExistingArticle(id=10, article_code="1", embedding_input="Раздел")]
    plan = compute_plan(parsed, existing)
    assert plan.inserts == []
    assert plan.updates == []
    assert plan.unchanged == 1


def test_update_invalidates_when_embedding_input_changed() -> None:
    parsed = [_p("1.1", "Новое имя", "1", "Раздел. Новое имя")]
    existing = [ExistingArticle(id=5, article_code="1.1", embedding_input="Раздел. Старое имя")]
    plan = compute_plan(parsed, existing)
    assert len(plan.updates) == 1
    assert plan.updates[0].invalidate_embedding is True
    assert plan.updates[0].id == 5


def test_delete_collects_missing_codes() -> None:
    parsed = [_p("1", "Раздел", None, "Раздел")]
    existing = [
        ExistingArticle(id=1, article_code="1", embedding_input="Раздел"),
        ExistingArticle(id=2, article_code="9", embedding_input="Удалить"),
    ]
    plan = compute_plan(parsed, existing)
    assert plan.delete_ids == [2]
    assert plan.delete_codes == ["9"]


def test_requires_force_on_root_deletion() -> None:
    plan = compute_plan(
        [],  # пустой файл -> всё существующее удаляется
        [ExistingArticle(id=1, article_code="1", embedding_input="Раздел верхнего уровня")],
    )
    # удаляется корневой узел "1"
    assert plan.delete_codes == ["1"]
    assert requires_force(plan, existing_total=1) is True


def test_no_force_for_first_import() -> None:
    plan = compute_plan([_p("1", "Раздел", None, "Раздел")], [])
    assert requires_force(plan, existing_total=0) is False


def test_no_force_for_small_leaf_deletion() -> None:
    existing = [
        ExistingArticle(id=i, article_code=f"1.{i}", embedding_input="x")
        for i in range(1, 11)
    ]
    # удаляем 1 из 10 листьев
    parsed = [_p(f"1.{i}", "x", "1", "x") for i in range(1, 10)]
    plan = compute_plan(parsed, existing)
    assert plan.delete_codes == ["1.10"]
    assert requires_force(plan, existing_total=10) is False
