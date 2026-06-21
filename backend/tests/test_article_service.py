from __future__ import annotations

import pytest

from app.domain.errors import DuplicateError, TemplateValidationError
from app.services.article_service import ArticleService
from tests.fakes import FakeRepository


def test_create_root_sets_embedding_input_to_name() -> None:
    svc = ArticleService(FakeRepository())
    article = svc.create(article_code="1", name="Раздел")
    assert article.embedding_input == "Раздел"
    assert article.parent_id is None
    assert article.embedding is None


def test_create_child_enriches_from_parent() -> None:
    repo = FakeRepository()
    svc = ArticleService(repo)
    svc.create(article_code="1", name="Раздел")
    child = svc.create(article_code="1.1", name="Лист", parent_code="1")
    assert child.embedding_input == "Раздел. Лист"
    assert child.parent_id == 1


def test_create_duplicate_code_raises() -> None:
    repo = FakeRepository()
    svc = ArticleService(repo)
    svc.create(article_code="1", name="Раздел")
    with pytest.raises(DuplicateError):
        svc.create(article_code="1", name="Дубль")


def test_create_node_that_would_be_ancestor_raises() -> None:
    repo = FakeRepository()
    svc = ArticleService(repo)
    svc.create(article_code="1", name="Раздел")
    svc.create(article_code="1.2.3", name="Глубокий лист", parent_code="1")
    # "1.2" стал бы предком уже существующего "1.2.3" — это запрещено (импорт only)
    with pytest.raises(TemplateValidationError):
        svc.create(article_code="1.2", name="Промежуточный", parent_code="1")


def test_create_rejects_non_numeric_code() -> None:
    # нечисловой код уронил бы GET /api/articles (cast в int[]) — отвергаем на входе
    with pytest.raises(TemplateValidationError):
        ArticleService(FakeRepository()).create(article_code="1a", name="Кривой")
