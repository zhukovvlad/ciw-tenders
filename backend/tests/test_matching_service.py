"""Тесты RAG-логики сопоставления (Шаг 3): пороги уверенности и арбитраж LLM."""

from __future__ import annotations

from app.domain.entities import ArticleCandidate, EstimateRow, MatchStatus, TemplateArticle
from app.services.matching_service import MatchingService
from tests.fakes import FakeEmbedder, FakeLLMMatcher, FakeRepository


def _article(code: str) -> TemplateArticle:
    return TemplateArticle(id=1, article_code=code, name=f"Работа {code}", section_name="Раздел")


def test_confident_match_when_score_above_threshold() -> None:
    candidates = [
        ArticleCandidate(article=_article("A"), score=0.95),
        ArticleCandidate(article=_article("B"), score=0.80),
    ]
    service = MatchingService(
        repository=FakeRepository(candidates),
        embedder=FakeEmbedder(),
        llm_matcher=FakeLLMMatcher(),
        confidence_threshold=0.90,
    )

    result = service.match_row(EstimateRow(row_number=2, name="Бетонные работы"))

    assert result.status is MatchStatus.CONFIDENT
    assert result.matched_article is not None
    assert result.matched_article.article_code == "A"


def test_needs_review_invokes_llm_when_score_below_threshold() -> None:
    candidates = [
        ArticleCandidate(article=_article("A"), score=0.70),
        ArticleCandidate(article=_article("B"), score=0.65),
    ]
    service = MatchingService(
        repository=FakeRepository(candidates),
        embedder=FakeEmbedder(),
        llm_matcher=FakeLLMMatcher(pick_index=1),  # LLM выбирает второго кандидата
        confidence_threshold=0.90,
    )

    result = service.match_row(EstimateRow(row_number=2, name="Кладка"))

    assert result.status is MatchStatus.NEEDS_REVIEW
    assert result.matched_article is not None
    assert result.matched_article.article_code == "B"


def test_no_match_when_repository_empty() -> None:
    service = MatchingService(
        repository=FakeRepository([]),
        embedder=FakeEmbedder(),
        llm_matcher=FakeLLMMatcher(),
    )

    result = service.match_row(EstimateRow(row_number=2, name="Неизвестная работа"))

    assert result.status is MatchStatus.NO_MATCH
    assert result.matched_article is None
