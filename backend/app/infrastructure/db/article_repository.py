"""Реализация ArticleRepository поверх PostgreSQL + pgvector.

Векторный поиск — косинусная дистанция `<=>`; similarity = 1 - distance (порог 0.90).
Сортировка списка — по коду численно (string_to_array(code,'.')::int[]), т.к. строковая
сортировка ломается на '1.10' vs '1.2'.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Integer, cast, delete, func, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from app.domain.catalog_tree import ancestor_names_by_ids
from app.domain.entities import ArticleCandidate, CatalogArticle, TemplateArticle
from app.domain.ports import ArticleRepository
from app.infrastructure.db.models import TemplateArticleModel

_CODE_ORDER = cast(func.string_to_array(TemplateArticleModel.article_code, "."), ARRAY(Integer))


class SqlAlchemyArticleRepository(ArticleRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _to_entity(model: TemplateArticleModel) -> TemplateArticle:
        return TemplateArticle(
            id=model.id,
            parent_id=model.parent_id,
            article_code=model.article_code,
            name=model.name,
            embedding_input=model.embedding_input,
            embedding=list(model.embedding) if model.embedding is not None else None,
        )

    def add(self, article: TemplateArticle) -> TemplateArticle:
        model = TemplateArticleModel(
            parent_id=article.parent_id,
            article_code=article.article_code,
            name=article.name,
            embedding_input=article.embedding_input,
            embedding=article.embedding,
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return self._to_entity(model)

    def get_by_code(self, code: str) -> TemplateArticle | None:
        stmt = select(TemplateArticleModel).where(TemplateArticleModel.article_code == code)
        model = self._session.scalars(stmt).one_or_none()
        return self._to_entity(model) if model is not None else None

    def get_by_id(self, article_id: int) -> TemplateArticle | None:
        model = self._session.get(TemplateArticleModel, article_id)
        return self._to_entity(model) if model is not None else None

    def list_all(self, limit: int = 100, offset: int = 0) -> list[TemplateArticle]:
        stmt = select(TemplateArticleModel).order_by(_CODE_ORDER).limit(limit).offset(offset)
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def delete(self, article_id: int) -> None:
        model = self._session.get(TemplateArticleModel, article_id)
        if model is not None:
            self._session.delete(model)
            self._session.commit()

    def delete_all(self) -> int:
        result = self._session.execute(delete(TemplateArticleModel))
        self._session.commit()
        return int(result.rowcount or 0)

    def has_descendant_codes(self, code: str) -> bool:
        prefix = code.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + ".%"
        stmt = select(TemplateArticleModel.id).where(
            TemplateArticleModel.article_code.like(prefix, escape="\\")
        ).limit(1)
        return self._session.scalars(stmt).first() is not None

    def search(self, q: str, limit: int = 20) -> list[TemplateArticle]:
        # экранируем LIKE-метасимволы в пользовательском вводе
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = (
            select(TemplateArticleModel)
            .where(
                TemplateArticleModel.article_code.ilike(like, escape="\\")
                | TemplateArticleModel.name.ilike(like, escape="\\")
            )
            .order_by(_CODE_ORDER)
            .limit(limit)
        )
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def search_similar(self, embedding: list[float], top_k: int = 3) -> list[ArticleCandidate]:
        distance = TemplateArticleModel.embedding.cosine_distance(embedding)
        stmt = (
            select(TemplateArticleModel, distance.label("distance"))
            .where(TemplateArticleModel.embedding.is_not(None))
            .order_by(distance)
            .limit(top_k)
        )
        return [
            ArticleCandidate(article=self._to_entity(model), score=1.0 - float(dist))
            for model, dist in self._session.execute(stmt)
        ]

    def matching_readiness(self) -> tuple[int, int]:
        total = self._session.scalar(select(func.count()).select_from(TemplateArticleModel)) or 0
        pending = self._session.scalar(
            select(func.count()).select_from(TemplateArticleModel).where(
                TemplateArticleModel.embedding.is_(None)
            )
        ) or 0
        return int(total), int(pending)

    def ancestor_names_by_ids(self, article_ids: Sequence[int]) -> dict[int, list[str]]:
        if not article_ids:
            return {}
        rows = self._session.execute(
            select(
                TemplateArticleModel.id,
                TemplateArticleModel.name,
                TemplateArticleModel.parent_id,
            )
        ).all()
        nodes = {r.id: (r.name, r.parent_id) for r in rows}
        return ancestor_names_by_ids(nodes, article_ids)

    def list_catalog(self) -> list[CatalogArticle]:
        """Весь справочник (id, code, name, parent_code) для промпта tree-движка."""
        rows = self._session.execute(
            select(
                TemplateArticleModel.id, TemplateArticleModel.article_code,
                TemplateArticleModel.name, TemplateArticleModel.parent_id,
            ).order_by(_CODE_ORDER)
        ).all()
        code_by_id = {r.id: r.article_code for r in rows}
        return [
            CatalogArticle(
                id=r.id, code=r.article_code, name=r.name,
                parent_code=code_by_id.get(r.parent_id) if r.parent_id else None,
            )
            for r in rows
        ]
