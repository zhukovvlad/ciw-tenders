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
    with pytest.raises(DuplicateError) as ei:
        svc.create(article_code="1", name="Дубль")
    assert ei.value.code == "article_code_exists"


def test_create_node_that_would_be_ancestor_raises() -> None:
    repo = FakeRepository()
    svc = ArticleService(repo)
    svc.create(article_code="1", name="Раздел")
    svc.create(article_code="1.2.3", name="Глубокий лист", parent_code="1")
    # "1.2" стал бы предком уже существующего "1.2.3" — это запрещено (импорт only)
    with pytest.raises(TemplateValidationError) as ei:
        svc.create(article_code="1.2", name="Промежуточный", parent_code="1")
    assert ei.value.code == "article_code_would_be_ancestor"


def test_create_rejects_non_numeric_code() -> None:
    # нечисловой код уронил бы GET /api/articles (cast в int[]) — отвергаем на входе
    with pytest.raises(TemplateValidationError) as ei:
        ArticleService(FakeRepository()).create(article_code="1a", name="Кривой")
    assert ei.value.code == "article_code_not_numeric"


def test_create_missing_parent_raises_validation() -> None:
    # несуществующий parent_code — ошибка ввода (маппится в 400), а не 500
    with pytest.raises(TemplateValidationError) as ei:
        ArticleService(FakeRepository()).create(article_code="1.1", name="Лист", parent_code="9")
    assert ei.value.code == "article_parent_not_found"


def test_delete_all_clears_and_returns_count() -> None:
    repo = FakeRepository()
    svc = ArticleService(repo)
    svc.create(article_code="1", name="Раздел")
    svc.create(article_code="2", name="Второй")
    assert svc.delete_all() == 2
    assert svc.list() == []
    assert svc.delete_all() == 0  # повторно — пусто, не ошибка
