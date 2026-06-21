"""SQL-реализация ArticleImportRepository: снимок + атомарное применение плана импорта.

apply_plan — две фазы резолва parent_id: сначала пишем строки с parent_id=NULL, затем по
карте code->id проставляем parent_id (порядок вставки не важен). Всё в одной транзакции.
"""

from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.domain.entities import ExistingArticle, ImportPlan
from app.domain.ports import ArticleImportRepository
from app.infrastructure.db.models import TemplateArticleModel


class SqlAlchemyArticleImportRepository(ArticleImportRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def load_existing(self) -> list[ExistingArticle]:
        stmt = select(
            TemplateArticleModel.id,
            TemplateArticleModel.article_code,
            TemplateArticleModel.embedding_input,
        )
        return [
            ExistingArticle(
                id=row.id, article_code=row.article_code, embedding_input=row.embedding_input
            )
            for row in self._session.execute(stmt)
        ]

    def apply_plan(self, plan: ImportPlan) -> None:
        try:
            if plan.delete_ids:
                self._session.execute(
                    delete(TemplateArticleModel).where(TemplateArticleModel.id.in_(plan.delete_ids))
                )
            for ins in plan.inserts:
                self._session.add(
                    TemplateArticleModel(
                        parent_id=None,
                        article_code=ins.article_code,
                        name=ins.name,
                        embedding_input=ins.embedding_input,
                        embedding=None,
                    )
                )
            for upd in plan.updates:
                values: dict[str, object] = {
                    "name": upd.name,
                    "embedding_input": upd.embedding_input,
                }
                if upd.invalidate_embedding:
                    values["embedding"] = None
                self._session.execute(
                    update(TemplateArticleModel)
                    .where(TemplateArticleModel.id == upd.id)
                    .values(**values)
                )
            self._session.flush()

            id_by_code = {
                code: _id
                for _id, code in self._session.execute(
                    select(TemplateArticleModel.id, TemplateArticleModel.article_code)
                )
            }
            for ins in plan.inserts:
                if ins.parent_code:
                    parent_id = id_by_code.get(ins.parent_code)
                    if parent_id is None:
                        raise ValueError(
                            f"Родитель '{ins.parent_code}' не найден для '{ins.article_code}'"
                        )
                    self._session.execute(
                        update(TemplateArticleModel)
                        .where(TemplateArticleModel.article_code == ins.article_code)
                        .values(parent_id=parent_id)
                    )
            for upd in plan.updates:
                parent_id = None
                if upd.parent_code is not None:
                    parent_id = id_by_code.get(upd.parent_code)
                    if parent_id is None:
                        raise ValueError(
                            f"Родитель '{upd.parent_code}' не найден для '{upd.article_code}'"
                        )
                self._session.execute(
                    update(TemplateArticleModel)
                    .where(TemplateArticleModel.id == upd.id)
                    .values(parent_id=parent_id)
                )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
