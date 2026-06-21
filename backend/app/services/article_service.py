"""Сервис управления справочником. Эмбеддинг не делает — вектор заполнит воркер."""

from __future__ import annotations

import re

from app.domain.entities import TemplateArticle
from app.domain.errors import DuplicateError, TemplateValidationError
from app.domain.ports import ArticleRepository


class ArticleService:
    def __init__(self, repository: ArticleRepository) -> None:
        self._repository = repository

    def create(
        self, article_code: str, name: str, parent_code: str | None = None
    ) -> TemplateArticle:
        if re.fullmatch(r"\d+(\.\d+)*", article_code) is None:
            raise TemplateValidationError(
                f"Код {article_code} должен состоять из числовых сегментов (напр. 1.4.1)"
            )
        if self._repository.get_by_code(article_code) is not None:
            raise DuplicateError(f"Статья с кодом {article_code} уже существует")
        if self._repository.has_descendant_codes(article_code):
            raise TemplateValidationError(
                f"Код {article_code} стал бы предком существующих статей — "
                "воспользуйтесь импортом справочника"
            )
        parent_id: int | None = None
        embedding_input = name
        if parent_code:
            parent = self._repository.get_by_code(parent_code)
            if parent is None:
                raise TemplateValidationError(f"Родитель с кодом {parent_code} не найден")
            parent_id = parent.id
            embedding_input = f"{parent.embedding_input}. {name}"
        article = TemplateArticle(
            article_code=article_code,
            name=name,
            embedding_input=embedding_input,
            parent_id=parent_id,
            embedding=None,
        )
        return self._repository.add(article)

    def list(self, limit: int = 100, offset: int = 0) -> list[TemplateArticle]:
        return self._repository.list_all(limit=limit, offset=offset)

    def delete(self, article_id: int) -> None:
        self._repository.delete(article_id)
