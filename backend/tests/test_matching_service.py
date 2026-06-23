from __future__ import annotations

from app.domain.entities import (
    ArticleCandidate,
    EstimateRowStatus,
    TemplateArticle,
)
from app.services.matching_service import MatchingService
from tests.fakes import FakeLLMMatcher, FakeRepository


def _article(aid: int, code: str) -> TemplateArticle:
    return TemplateArticle(
        id=aid, article_code=code, name=f"имя {code}", embedding_input=f"ei {code}"
    )


def _svc(candidates, llm=None, threshold=0.90):
    repo = FakeRepository(candidates=candidates)
    return MatchingService(
        repo, embedder=None, llm_matcher=llm or FakeLLMMatcher(), confidence_threshold=threshold
    )


def test_no_candidates_is_no_match() -> None:
    nm = _svc([]).match_one([0.1, 0.2], "запрос")
    assert nm.status is EstimateRowStatus.NO_MATCH and nm.score is None and nm.candidates == []


def test_high_score_is_confident_top1() -> None:
    cands = [ArticleCandidate(_article(1, "1.1"), 0.97), ArticleCandidate(_article(2, "1.2"), 0.5)]
    nm = _svc(cands).match_one([0.1], "запрос")
    assert nm.status is EstimateRowStatus.CONFIDENT
    assert nm.matched_id == 1 and nm.matched_code == "1.1" and nm.score == 0.97
    assert [c.id for c in nm.candidates] == [1, 2]  # снимок топ-K с id


def test_low_score_llm_pick_is_needs_review_with_chosen_score() -> None:
    cands = [ArticleCandidate(_article(1, "1.1"), 0.80), ArticleCandidate(_article(2, "1.2"), 0.70)]
    nm = _svc(cands, llm=FakeLLMMatcher(pick_index=1)).match_one([0.1], "запрос")
    assert nm.status is EstimateRowStatus.NEEDS_REVIEW
    assert nm.matched_id == 2 and nm.score == 0.70  # косинус ВЫБРАННОГО, не top-1


def test_llm_declines_is_no_match_keeps_candidates() -> None:
    cands = [ArticleCandidate(_article(1, "1.1"), 0.80)]

    class _Decline(FakeLLMMatcher):
        def choose_best(self, query, candidates):
            return None

    nm = _svc(cands, llm=_Decline()).match_one([0.1], "запрос")
    assert nm.status is EstimateRowStatus.NO_MATCH and nm.score is None
    assert len(nm.candidates) == 1  # кандидаты сохранены для SP3


def test_llm_hallucinated_article_treated_as_decline() -> None:
    cands = [ArticleCandidate(_article(1, "1.1"), 0.80)]

    class _Halluc(FakeLLMMatcher):
        def choose_best(self, query, candidates):
            return TemplateArticle(id=999, article_code="9.9", name="фейк", embedding_input="x")

    nm = _svc(cands, llm=_Halluc()).match_one([0.1], "запрос")
    assert nm.status is EstimateRowStatus.NO_MATCH  # не из кандидатов → как отказ
