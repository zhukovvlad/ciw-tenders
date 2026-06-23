"""Сценарий правки решения ревью (SP3). Зависит только от портов.

Пишет ось ревью (review_status/final_*), НЕ трогает AI-снимок (matched_*/candidates).
final_* морозятся в момент решения: кандидат → из снимка; ручной подбор → из справочника.
"""

from __future__ import annotations

from app.domain.entities import ReviewStatus, StoredEstimateRow
from app.domain.errors import InvalidReviewActionError, RowNotMatchedError
from app.domain.ports import ArticleRepository, EstimateRepository

_PENDING = "pending"


class EstimateReviewService:
    def __init__(self, estimates: EstimateRepository, articles: ArticleRepository) -> None:
        self._estimates = estimates
        self._articles = articles

    def apply(
        self,
        estimate_id: int,
        row_id: int,
        action: str,
        article_id: int | None,
        requester_id: int,
        *,
        is_admin: bool,
    ) -> StoredEstimateRow:
        est = self._estimates.get(estimate_id, requester_id, is_admin=is_admin)
        if est is None:
            raise LookupError("Смета не найдена")  # роут → 404
        row = next((r for r in est.rows if r.id == row_id), None)
        if row is None:
            raise LookupError("Строка не найдена")
        if row.status == _PENDING:
            raise RowNotMatchedError("Строка ещё не сматчена")

        if action == "confirm":
            self._confirm(row)
        elif action == "pick":
            self._pick(row, article_id)
        elif action == "reject":
            self._reject(row_id)
        else:
            raise InvalidReviewActionError(f"Неизвестное действие: {action!r}")

        updated = self._estimates.get(estimate_id, requester_id, is_admin=is_admin)
        assert updated is not None
        return next(r for r in updated.rows if r.id == row_id)

    def _confirm(self, row: StoredEstimateRow) -> None:
        if row.matched_article_id is None:
            raise InvalidReviewActionError("Нет рекомендации AI — confirm недоступен")
        self._estimates.save_review_decision(
            row.id, review_status=str(ReviewStatus.CONFIRMED),
            final_article_id=row.matched_article_id,
            final_code=row.matched_code, final_name=row.matched_name,
        )

    def _pick(self, row: StoredEstimateRow, article_id: int | None) -> None:
        if article_id is None:
            raise InvalidReviewActionError("pick требует article_id")
        cand = next((c for c in row.candidates if c.id == article_id), None)
        if cand is not None:
            code, name = cand.code, cand.name
        else:
            art = self._articles.get_by_id(article_id)
            if art is None:
                raise InvalidReviewActionError("Статья не найдена")
            code, name = art.article_code, art.name
        status = (
            ReviewStatus.CONFIRMED
            if article_id == row.matched_article_id
            else ReviewStatus.OVERRIDDEN
        )
        self._estimates.save_review_decision(
            row.id, review_status=str(status),
            final_article_id=article_id, final_code=code, final_name=name,
        )

    def _reject(self, row_id: int) -> None:
        self._estimates.save_review_decision(
            row_id, review_status=str(ReviewStatus.REJECTED),
            final_article_id=None, final_code=None, final_name=None,
        )
