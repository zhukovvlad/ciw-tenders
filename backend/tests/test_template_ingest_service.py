from __future__ import annotations

import io

import pandas as pd
import pytest

from app.domain.errors import DeletionGuardError, TemplateValidationError
from app.services.template_ingest_service import TemplateIngestService
from app.services.template_parser import TemplateParser
from tests.fakes import FakeImportRepository


def _xlsx(values: list[str]) -> bytes:
    df = pd.DataFrame({0: values})
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, header=False, engine="openpyxl")
    return buffer.getvalue()


def _service(repo: FakeImportRepository) -> TemplateIngestService:
    return TemplateIngestService(parser=TemplateParser(), repository=repo)


def test_first_import_creates_all_pending() -> None:
    repo = FakeImportRepository()
    report = _service(repo).import_template(_xlsx(["(1.) Раздел", "(1.1.) Под"]))
    assert report.created == 2
    assert report.deleted == 0
    assert report.pending_embeddings == 2
    assert {a.article_code for a in repo.rows.values()} == {"1", "1.1"}


def test_import_resolves_parent_id() -> None:
    # фейк, как и SQL-адаптер, проставляет parent_id во второй фазе (резолв code->id)
    repo = FakeImportRepository()
    _service(repo).import_template(_xlsx(["(1.) Раздел", "(1.1.) Под"]))
    assert repo.get("1").parent_id is None
    assert repo.get("1.1").parent_id == repo.get("1").id


def test_reimport_unchanged_keeps_embedding() -> None:
    repo = FakeImportRepository()
    _service(repo).import_template(_xlsx(["(1.) Раздел"]))
    repo.set_embedding("1", [0.1, 0.2, 0.3])  # эмулируем работу воркера
    report = _service(repo).import_template(_xlsx(["(1.) Раздел"]))
    assert report.unchanged == 1
    assert repo.get("1").embedding == [0.1, 0.2, 0.3]


def test_ancestor_rename_invalidates_descendant() -> None:
    repo = FakeImportRepository()
    _service(repo).import_template(_xlsx(["(1.) Старое", "(1.1.) Лист"]))
    repo.set_embedding("1.1", [9.0])
    report = _service(repo).import_template(_xlsx(["(1.) Новое", "(1.1.) Лист"]))
    # корень "1" (сменил имя) + потомок "1.1" (его embedding_input изменился из-за предка)
    assert report.updated == 2
    assert repo.get("1.1").embedding is None


def test_dry_run_writes_nothing() -> None:
    repo = FakeImportRepository()
    report = _service(repo).import_template(_xlsx(["(1.) Раздел"]), dry_run=True)
    assert report.dry_run is True
    assert report.created == 1
    assert report.force_required is False
    assert repo.rows == {}


def test_dry_run_flags_force_required_without_writing() -> None:
    repo = FakeImportRepository()
    _service(repo).import_template(_xlsx(["(1.) Раздел", "(2.) Второй"]))
    # dry-run импорта, который снёс бы корень "2": предупреждаем, но не пишем и не бросаем
    report = _service(repo).import_template(_xlsx(["(1.) Раздел"]), dry_run=True)
    assert report.dry_run is True
    assert report.deleted == 1
    assert report.force_required is True
    assert {a.article_code for a in repo.rows.values()} == {"1", "2"}  # ничего не удалено


def test_root_deletion_requires_force() -> None:
    repo = FakeImportRepository()
    _service(repo).import_template(_xlsx(["(1.) Раздел", "(2.) Второй"]))
    with pytest.raises(DeletionGuardError):
        _service(repo).import_template(_xlsx(["(1.) Раздел"]))  # сносит корень "2"


def test_root_deletion_with_force_applies() -> None:
    repo = FakeImportRepository()
    _service(repo).import_template(_xlsx(["(1.) Раздел", "(2.) Второй"]))
    report = _service(repo).import_template(_xlsx(["(1.) Раздел"]), force=True)
    assert report.deleted == 1
    assert {r.article_code for r in repo.rows.values()} == {"1"}


def test_orphan_file_raises() -> None:
    repo = FakeImportRepository()
    with pytest.raises(TemplateValidationError):
        _service(repo).import_template(_xlsx(["(1.) Раздел", "(2.5.) Сирота"]))
