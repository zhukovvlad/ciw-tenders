"""Сервис сопоставления строк сметы с эталонным справочником (RAG-ядро).

Алгоритм (Шаг 3 ТЗ):
  1. Векторизуем строку (Embedder → Gemini).
  2. Ищем топ-3 ближайших статьи в БД (ArticleRepository → pgvector).
  3. score > threshold      -> "Уверенное совпадение".
     score <= threshold     -> LLM-арбитр (Anthropic) выбирает из топ-3 -> "Требует проверки".

Сервис не знает о конкретных Gemini/Anthropic/Postgres — только о портах.
"""

from __future__ import annotations

from app.domain.entities import EstimateRow, MatchResult, MatchStatus
from app.domain.ports import ArticleRepository, Embedder, LLMMatcher


class MatchingService:
    def __init__(
        self,
        repository: ArticleRepository,
        embedder: Embedder,
        llm_matcher: LLMMatcher,
        confidence_threshold: float = 0.90,
        top_k: int = 3,
    ) -> None:
        self._repository = repository
        self._embedder = embedder
        self._llm_matcher = llm_matcher
        self._threshold = confidence_threshold
        self._top_k = top_k

    def match_row(self, row: EstimateRow) -> MatchResult:
        embedding = self._embedder.embed(row.name)
        candidates = self._repository.search_similar(embedding, top_k=self._top_k)

        if not candidates:
            return MatchResult(
                source_row=row,
                matched_article=None,
                status=MatchStatus.NO_MATCH,
                score=0.0,
                candidates=[],
            )

        best = candidates[0]

        if best.score > self._threshold:
            return MatchResult(
                source_row=row,
                matched_article=best.article,
                status=MatchStatus.CONFIDENT,
                score=best.score,
                candidates=candidates,
            )

        # Низкая уверенность — отдаём топ-K на арбитраж LLM.
        chosen = self._llm_matcher.choose_best(row.name, candidates)
        return MatchResult(
            source_row=row,
            matched_article=chosen,
            status=MatchStatus.NEEDS_REVIEW,
            score=best.score,
            candidates=candidates,
        )

    def match_rows(self, rows: list[EstimateRow]) -> list[MatchResult]:
        return [self.match_row(row) for row in rows]
