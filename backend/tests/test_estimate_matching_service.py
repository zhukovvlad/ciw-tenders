from __future__ import annotations

from app.domain.entities import (
    ArticleCandidate,
    EstimateNode,
    EstimateStatus,
    NewEstimate,
    TemplateArticle,
)
from app.domain.errors import DictionaryNotReadyError, TransientError
from app.services.estimate_matching_service import EstimateMatchingService
from app.services.matching_service import MatchingService
from tests.fakes import FakeEstimateRepository, FakeLLMMatcher, FakeRepository


def _node(code: str) -> EstimateNode:
    return EstimateNode(code, f"имя {code}", None, "СМР", f"ei {code}", 0, 1)


_MISSING: list[float] = []  # sentinel: отличает «не передан» от «явно None»


def _article(aid: int, code: str, emb: list[float] | None = _MISSING) -> TemplateArticle:  # type: ignore[assignment]
    embedding = [0.1] if emb is _MISSING else emb
    return TemplateArticle(id=aid, article_code=code, name=f"имя {code}",
                           embedding_input=f"ei {code}", embedding=embedding)


class _Embedder:
    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def embed(self, text):  # не используется
        return [0.1]

    def embed_batch(self, texts):
        self.batches.append(list(texts))
        return [[0.1, float(len(t) % 5)] for t in texts]


def _service(repo, articles, *, embedder=None, llm=None):
    matcher = MatchingService(articles, embedder=None, llm_matcher=llm or FakeLLMMatcher())
    return EstimateMatchingService(matcher=matcher, embedder=embedder or _Embedder(),
                                   estimates=repo, articles=articles)


def _ready_articles(candidates) -> FakeRepository:
    art = FakeRepository(candidates=candidates)
    art._store.append(_article(1, "1.1"))  # total>0, pending==0 (embedding задан в _article)
    return art


def test_blocked_when_dictionary_empty_raises() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    art = FakeRepository(candidates=[])  # total==0
    import pytest
    with pytest.raises(DictionaryNotReadyError):
        _service(repo, art).match_estimate(est.id)
    # embed-шаг всё равно прошёл (узлы заэмбежены — не впустую)
    assert all(n["embedding"] is not None for n in repo.nodes.values())


def test_blocked_when_articles_pending_raises() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    art = FakeRepository(candidates=[])
    art._store.append(_article(1, "1.1", emb=None))  # pending>0
    import pytest
    with pytest.raises(DictionaryNotReadyError):
        _service(repo, art).match_estimate(est.id)


def test_happy_path_ready_with_confident() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    art = _ready_articles([ArticleCandidate(_article(1, "1.1"), 0.97)])
    _service(repo, art).match_estimate(est.id)
    assert repo.get_status(est.id) == EstimateStatus.READY
    assert next(iter(repo.nodes.values()))["status"] == "confident"


def test_locked_estimate_is_noop() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    repo.try_matching_lock(est.id)  # держим лок «другим воркером»
    art = _ready_articles([ArticleCandidate(_article(1, "1.1"), 0.97)])
    _service(repo, art).match_estimate(est.id)
    assert repo.get_status(est.id) == "pending"  # ничего не сделано


def test_node_transient_becomes_error_partial() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    art = _ready_articles([ArticleCandidate(_article(1, "1.1"), 0.5)])

    class _BoomLLM(FakeLLMMatcher):
        def choose_best(self, query, candidates):
            raise TransientError("429")

    _service(repo, art, llm=_BoomLLM()).match_estimate(est.id)
    assert repo.get_status(est.id) == EstimateStatus.PARTIAL_ERROR
    assert next(iter(repo.nodes.values()))["status"] == "error"


def test_mark_blocked_noop_if_terminal() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    repo.set_status(est.id, EstimateStatus.READY)
    _service(repo, _ready_articles([])).mark_blocked(est.id, "timeout")
    assert repo.get_status(est.id) == EstimateStatus.READY  # не затёрли результат


def test_mark_blocked_sets_blocked_when_not_terminal() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    _service(repo, _ready_articles([])).mark_blocked(est.id, "timeout")
    assert repo.get_status(est.id) == EstimateStatus.BLOCKED


def test_unexpected_error_sets_partial_error_and_reraises() -> None:
    import pytest

    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    art = _ready_articles([ArticleCandidate(_article(1, "1.1"), 0.5)])

    class _BugLLM(FakeLLMMatcher):
        def choose_best(self, query, candidates):
            raise ValueError("неожиданный баг")  # НЕ транзиент и не gate

    with pytest.raises(ValueError):
        _service(repo, art, llm=_BugLLM()).match_estimate(est.id)
    # смета не залипла в running — переведена в partial_error
    assert repo.get_status(est.id) == EstimateStatus.PARTIAL_ERROR
    # лок отпущен в finally → можно взять снова
    assert repo.try_matching_lock(est.id) is True
