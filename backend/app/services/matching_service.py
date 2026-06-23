"""Ядро сопоставления узла со справочником (RAG: retrieval + LLM-арбитраж).

Принимает ГОТОВЫЙ вектор узла (не ре-эмбеддит). query_text (= embedding_input узла) идёт
только в LLM-арбитр. Возвращает NodeMatch со слаг-статусом и снимком кандидатов.
"""

from __future__ import annotations

from app.domain.entities import (
    ArticleCandidate,
    EstimateRowStatus,
    MatchCandidate,
    NodeMatch,
    TemplateArticle,
)
from app.domain.ports import ArticleRepository, Embedder, LLMMatcher


def _snapshot(candidates: list[ArticleCandidate]) -> list[MatchCandidate]:
    return [
        MatchCandidate(
            id=c.article.id, code=c.article.article_code, name=c.article.name, score=c.score
        )
        for c in candidates
    ]


class MatchingService:
    def __init__(
        self,
        repository: ArticleRepository,
        embedder: Embedder | None = None,  # больше не используется ядром (сметы хранят вектор)
        llm_matcher: LLMMatcher | None = None,
        confidence_threshold: float = 0.90,
        top_k: int = 3,
    ) -> None:
        self._repository = repository
        self._llm_matcher = llm_matcher
        self._threshold = confidence_threshold
        self._top_k = top_k

    def match_one(self, embedding: list[float], query_text: str) -> NodeMatch:
        candidates = self._repository.search_similar(embedding, top_k=self._top_k)
        if not candidates:
            return NodeMatch(EstimateRowStatus.NO_MATCH)
        snap = _snapshot(candidates)
        best = candidates[0]
        if best.score > self._threshold:
            return NodeMatch(
                EstimateRowStatus.CONFIDENT, best.article.id, best.article.article_code,
                best.article.name, best.score, snap,
            )
        chosen = (
            self._llm_matcher.choose_best(query_text, candidates) if self._llm_matcher else None
        )
        chosen_score = self._score_of(chosen, candidates)
        if chosen is None or chosen_score is None:   # отказ / галлюцинация вне кандидатов
            return NodeMatch(EstimateRowStatus.NO_MATCH, candidates=snap)
        return NodeMatch(
            EstimateRowStatus.NEEDS_REVIEW, chosen.id, chosen.article_code,
            chosen.name, chosen_score, snap,
        )

    @staticmethod
    def _score_of(
        chosen: TemplateArticle | None, candidates: list[ArticleCandidate]
    ) -> float | None:
        if chosen is None:
            return None
        for c in candidates:                          # валидация: chosen ДОЛЖЕН быть из кандидатов
            if c.article.id == chosen.id and c.article.article_code == chosen.article_code:
                return c.score
        return None                                   # «придуманная» статья → трактуем как отказ
