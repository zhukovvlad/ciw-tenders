from __future__ import annotations

from app.domain.classification import CRUMB_DERIVATION_VERSION
from app.domain.decision_fund import FundHit, cache_key_hash, normalize_cache_key
from app.domain.entities import (
    ArticleCandidate,
    EstimateNode,
    EstimateStatus,
    NewEstimate,
    NodeClassification,
    TemplateArticle,
    WorkClass,
)
from app.domain.errors import DictionaryNotReadyError, TransientError
from app.services.estimate_matching_service import EstimateMatchingService
from app.services.matching_service import MatchingService
from tests.fakes import (
    FakeDecisionFundRepository,
    FakeEmbedder,
    FakeEstimateRepository,
    FakeLLMMatcher,
    FakeRepository,
    FakeWorkTypeClassifier,
)


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
                                   estimates=repo, articles=articles,
                                   classifier=FakeWorkTypeClassifier(default=WorkClass.WORK),
                                   fund=FakeDecisionFundRepository())


def _matching_service(repo, articles, fund, apply_fund: bool = True, embedder=None):
    matcher = MatchingService(articles, embedder=None, llm_matcher=FakeLLMMatcher())
    return EstimateMatchingService(matcher=matcher, embedder=embedder or _Embedder(),
                                   estimates=repo, articles=articles,
                                   classifier=FakeWorkTypeClassifier(default=WorkClass.WORK),
                                   fund=fund, apply_fund=apply_fund)


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


# ---------------------------------------------------------------------------
# Task 7: fake_repo tests for NodeClassification persistence
# ---------------------------------------------------------------------------


def _seed_one(repo: FakeEstimateRepository, name: str) -> int:
    est = repo.create(
        NewEstimate(user_id=1, filename="f.xlsx", original_object_key="k"),
        [EstimateNode(code="1", name=name, parent_code=None, section_type=None,
                      embedding_input=name, source_index=0, depth=1)],
    )
    return est.rows[0].id


def test_fake_repo_excludes_marked_org() -> None:
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "1 Этап ЖК")
    repo.save_node_classifications(
        [NodeClassification(nid, excluded=True, embedding_input="1 Этап ЖК")]
    )
    assert repo.fetch_unembedded_nodes(1, after_id=0, limit=10) == []
    assert repo.count_unfinished_nodes(1) == 0
    assert repo.list_for_owner(1, is_admin=True)[0].nodes_count == 0


def test_fake_repo_survivor_keeps_pending_and_new_breadcrumb() -> None:
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "x")
    repo.save_node_classifications(
        [NodeClassification(nid, excluded=False, embedding_input="Чистая крошка")]
    )
    pend = repo.fetch_unembedded_nodes(1, after_id=0, limit=10)
    assert pend[0].embedding_input == "Чистая крошка"
    assert repo.count_unfinished_nodes(1) == 1


def test_fake_repo_classification_never_clobbers_matched_status() -> None:
    # охрана: переклассификация на повторном прогоне не трогает терминальный матч-статус
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "Устройство кровли")
    repo.nodes[nid]["status"] = "confident"  # как будто уже сматчено
    repo.save_node_classifications([NodeClassification(nid, excluded=True, embedding_input="x")])
    assert repo.get(1, 1, is_admin=True).rows[0].status == "confident"


def test_fake_repo_excluded_flips_back_to_pending() -> None:
    # узел, ошибочно исключённый в прошлый прогон, на этом возвращается в матчинг
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "x")
    repo.save_node_classifications([NodeClassification(nid, excluded=True, embedding_input="x")])
    repo.save_node_classifications([NodeClassification(nid, excluded=False, embedding_input="x")])
    assert repo.count_unfinished_nodes(1) == 1  # снова pending


def test_fake_repo_reclassifies_error_node_to_excluded() -> None:
    # охрана расширена до error/no_match: орг-строка, осевшая в error на прошлом прогоне,
    # на этом переклассифицируется в excluded (иначе осталась бы матчабельной и засоряла).
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "1 Этап ЖК")
    repo.nodes[nid]["status"] = "error"
    repo.save_node_classifications(
        [NodeClassification(nid, excluded=True, embedding_input="1 Этап ЖК")]
    )
    assert repo.get(1, 1, is_admin=True).rows[0].status == "excluded"


def test_fake_repo_reclassify_clears_vector_when_breadcrumb_changes() -> None:
    # уже сэмбедженный узел + изменившаяся крошка (флип вердикта предка на ре-прогоне) →
    # старый вектор сбрасывается, узел снова попадает в очередь эмбеддинга (нет дрейфа).
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "x")
    repo.nodes[nid]["embedding"] = [1.0, 0.0, 0.0]
    repo.save_node_classifications(
        [NodeClassification(nid, excluded=False, embedding_input="Новая крошка")]
    )
    assert repo.nodes[nid]["embedding"] is None
    pend = repo.fetch_unembedded_nodes(1, after_id=0, limit=10)
    assert pend and pend[0].embedding_input == "Новая крошка"


def test_fake_repo_reclassify_resets_unreviewed_matched_fund() -> None:
    # отравленный фонд лечится: ре-прогон возвращает нетронутый фонд-хит в pending (спека §12.3)
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "x")
    repo.nodes[nid]["status"] = "matched_fund"
    repo.save_node_classifications([NodeClassification(nid, excluded=False, embedding_input="x")])
    assert repo.get(1, 1, is_admin=True).rows[0].status == "pending"


def test_fake_repo_reclassify_keeps_reviewed_matched_fund() -> None:
    # решение человека поверх фонд-хита неприкосновенно
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "x")
    repo.nodes[nid]["status"] = "matched_fund"
    repo.nodes[nid]["review_status"] = "confirmed"
    repo.save_node_classifications([NodeClassification(nid, excluded=False, embedding_input="x")])
    assert repo.get(1, 1, is_admin=True).rows[0].status == "matched_fund"


def test_rematch_after_fund_cleanup_reresolves_row() -> None:
    # строка проштампована фондом → запись фонда сняли → повторный полный прогон даёт RAG-результат
    repo = FakeEstimateRepository()
    fund = FakeDecisionFundRepository()
    est = repo.create(NewEstimate(1, "f.xlsx", "k"),
                      [EstimateNode("1.1.5", "МОКАП", "1.1", None, "МОКАП", 0, 3)])
    key = cache_key_hash(normalize_cache_key("МОКАП"))
    fund.seed_hit(key, CRUMB_DERIVATION_VERSION, FundHit(5, "1.4", "Мокап"))
    art = _ready_articles([ArticleCandidate(_article(9, "1.99"), 0.97)])
    svc = _matching_service(repo, art, fund, apply_fund=True)
    svc.match_estimate(est.id)
    assert repo.get(est.id, 1, is_admin=True).rows[0].status == "matched_fund"
    fund.clear()  # плохую запись сняли (unreference + rebuild)
    svc.match_estimate(est.id)
    row = repo.get(est.id, 1, is_admin=True).rows[0]
    assert row.status == "confident" and row.matched_article_id == 9  # переразрешено RAG-ом


def test_fake_repo_reclassify_keeps_vector_when_breadcrumb_unchanged() -> None:
    # крошка не изменилась → вектор сохраняется, лишний пере-эмбед не провоцируется.
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "x")  # embedding_input == "x"
    repo.nodes[nid]["embedding"] = [1.0, 0.0, 0.0]
    repo.save_node_classifications([NodeClassification(nid, excluded=False, embedding_input="x")])
    assert repo.nodes[nid]["embedding"] == [1.0, 0.0, 0.0]
    assert repo.fetch_unembedded_nodes(1, after_id=0, limit=10) == []


# ---------------------------------------------------------------------------
# Task 8: classify_nodes orchestration tests
# ---------------------------------------------------------------------------


def _two_node_estimate(repo: FakeEstimateRepository) -> int:
    # дерево: «1 Этап ЖК» (ORG) → «1.1 Устройство кровли» (WORK)
    est = repo.create(
        NewEstimate(user_id=1, filename="f.xlsx", original_object_key="k"),
        [
            EstimateNode(code="1", name="1 Этап ЖК", parent_code=None,
                         section_type=None, embedding_input="1 Этап ЖК",
                         source_index=0, depth=1),
            EstimateNode(code="1.1", name="Устройство кровли", parent_code="1",
                         section_type=None, embedding_input="1 Этап ЖК. Устройство кровли",
                         source_index=1, depth=2),
        ],
    )
    return est.id


def _classify_service(
    repo: FakeEstimateRepository, articles: FakeRepository
) -> EstimateMatchingService:
    matcher = MatchingService(articles, embedder=None, llm_matcher=None, confidence_threshold=0.9)
    return EstimateMatchingService(
        matcher=matcher,
        embedder=FakeEmbedder(),
        estimates=repo,
        articles=articles,
        classifier=FakeWorkTypeClassifier(default=WorkClass.WORK),
        fund=FakeDecisionFundRepository(),
    )


def test_classify_excludes_org_and_strips_breadcrumb() -> None:
    repo = FakeEstimateRepository()
    articles = FakeRepository(candidates=[])
    articles.add(TemplateArticle(article_code="1", name="Кровля",
                                 embedding_input="Кровля", embedding=[1.0, 1.0, 0.0]))
    eid = _two_node_estimate(repo)

    svc = _classify_service(repo, articles)
    svc._classify_nodes(eid)  # noqa: SLF001 — целевой метод под тестом

    rows = {r.code: r for r in repo.get(eid, 1, is_admin=True).rows}
    # «1 Этап ЖК» — чистый каркас → ORG лексикой (без обращения к classifier) → excluded
    assert rows["1"].status == "excluded"
    # потомок-работа выжил, а ORG-предок вырезан из крошки
    assert rows["1.1"].status == "pending"
    assert rows["1.1"].embedding_input == "Устройство кровли"


def test_llm_org_verdict_on_mixed_also_excludes() -> None:
    # ORG из ВЕРДИКТА LLM (а не лексики) тоже обязан давать excluded.
    repo = FakeEstimateRepository()
    articles = FakeRepository(candidates=[])
    est = repo.create(
        NewEstimate(user_id=1, filename="f.xlsx", original_object_key="k"),
        [EstimateNode(code="1", name="Гостиница Заря 1 Этап", parent_code=None,
                      section_type=None, embedding_input="Гостиница Заря 1 Этап",
                      source_index=0, depth=1)],
    )
    # «... 1 Этап» — смесь (оргтокен + голова «Гостиница») → UNSURE лексикой → LLM.
    clf = FakeWorkTypeClassifier(verdicts={"Гостиница Заря 1 Этап": WorkClass.ORG})
    matcher = MatchingService(articles, embedder=None, llm_matcher=None, confidence_threshold=0.9)
    svc = EstimateMatchingService(
        matcher=matcher, embedder=FakeEmbedder(), estimates=repo,
        articles=articles, classifier=clf, fund=FakeDecisionFundRepository(),
    )
    svc._classify_nodes(est.id)  # noqa: SLF001
    assert repo.get(est.id, 1, is_admin=True).rows[0].status == "excluded"
    assert clf.calls  # LLM действительно вызван по смеси


def test_duplicate_code_excludes_only_scaffold() -> None:
    # Две строки с ОДНИМ кодом: работа + каркас. Класс по id, не по коду →
    # исключается только каркас, «Земляные работы» НЕ теряются молча.
    repo = FakeEstimateRepository()
    articles = FakeRepository(candidates=[])
    est = repo.create(
        NewEstimate(user_id=1, filename="f.xlsx", original_object_key="k"),
        [
            EstimateNode(code="1.2", name="Земляные работы", parent_code="1",
                         section_type=None, embedding_input="Земляные работы",
                         source_index=0, depth=2),
            EstimateNode(code="1.2", name="1 Этап ЖК", parent_code="1",
                         section_type=None, embedding_input="1 Этап ЖК",
                         source_index=1, depth=2),
        ],
    )
    svc = _classify_service(repo, articles)  # FakeWorkTypeClassifier(default=WorkClass.WORK)
    svc._classify_nodes(est.id)  # noqa: SLF001
    by_name = {r.name: r for r in repo.get(est.id, 1, is_admin=True).rows}
    assert by_name["Земляные работы"].status == "pending"   # работа выжила
    assert by_name["1 Этап ЖК"].status == "excluded"        # каркас исключён


# ---------------------------------------------------------------------------
# Task 7: per-estimate summary logging
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Task 2: org-leaf rescue — override в _classify_nodes
# ---------------------------------------------------------------------------


def _seed_tree(repo: FakeEstimateRepository, tree: list[tuple[str, str, str | None]]):
    """tree: список (code, name, parent_code) в порядке сметы (source_index = индекс)."""
    nodes = [
        EstimateNode(code=c, name=nm, parent_code=p, section_type=None,
                     embedding_input=nm, source_index=i, depth=c.count(".") + 1)
        for i, (c, nm, p) in enumerate(tree)
    ]
    return repo.create(NewEstimate(user_id=1, filename="f.xlsx", original_object_key="k"), nodes)


def _classify_svc(repo, *, classifier):
    art = _ready_articles([])
    matcher = MatchingService(art, embedder=None, llm_matcher=FakeLLMMatcher())
    return EstimateMatchingService(matcher=matcher, embedder=_Embedder(),
                                   estimates=repo, articles=art, classifier=classifier,
                                   fund=FakeDecisionFundRepository())


def test_classify_rescues_org_leaf_under_work():
    repo = FakeEstimateRepository()
    est = _seed_tree(repo, [
        ("1", "Подготовительные работы", None),   # WORK (лексика)
        ("1.1", "Корпус 8", "1"),                  # ORG-лист под work → СПАСТИ
        ("2", "1 Этап ЖК", None),                  # ORG, нет work-предка → excluded
        ("2.1", "Монтаж кровли", "2"),             # WORK-ребёнок 2 (делает 2 не-листом)
    ])
    svc = _classify_svc(repo, classifier=FakeWorkTypeClassifier(default=WorkClass.WORK))
    svc._classify_nodes(est.id)
    by_code = {r.code: r for r in repo.get(est.id, 1, is_admin=True).rows}
    assert by_code["1.1"].status == "pending"                    # спасён (не excluded)
    assert by_code["1.1"].embedding_input == "Подготовительные работы"  # свой org-токен выброшен
    assert by_code["2"].status == "excluded"                     # не-лист org-разделитель
    assert by_code["1"].status == "pending" and by_code["2.1"].status == "pending"
    assert by_code["2.1"].embedding_input == "Монтаж кровли"      # ORG-предок «1 Этап ЖК» выброшен


def test_classify_org_leaf_without_work_ancestor_excluded():
    repo = FakeEstimateRepository()
    est = _seed_tree(repo, [
        ("1", "1 Этап ЖК", None),     # ORG-корень (нет предков)
        ("1.1", "Корпус 8", "1"),     # ORG-лист, единственный предок ORG → нет non-org → excluded
    ])
    svc = _classify_svc(repo, classifier=FakeWorkTypeClassifier(default=WorkClass.WORK))
    svc._classify_nodes(est.id)
    by_code = {r.code: r for r in repo.get(est.id, 1, is_admin=True).rows}
    assert by_code["1.1"].status == "excluded"


def test_classify_unsure_ancestor_counts_as_non_org():
    # регресс: предок UNSURE (НЕ WORK) — non-org, спасение org-листа под ним должно сработать.
    repo = FakeEstimateRepository()
    est = _seed_tree(repo, [
        ("1", "Смешанный узел ЖК", None),   # орг-токен ЖК + голова → UNSURE → классификатор
        ("1.1", "Корпус 8", "1"),           # ORG-лист под UNSURE-предком → СПАСТИ
    ])
    clf = FakeWorkTypeClassifier(
        verdicts={"Смешанный узел ЖК": WorkClass.UNSURE}, default=WorkClass.UNSURE
    )
    svc = _classify_svc(repo, classifier=clf)
    svc._classify_nodes(est.id)
    by_code = {r.code: r for r in repo.get(est.id, 1, is_admin=True).rows}
    assert by_code["1.1"].status == "pending"   # спасён через UNSURE-предка
    assert by_code["1.1"].embedding_input == "Смешанный узел ЖК"  # UNSURE-предок в крошке, свой org вне  # noqa: E501


def test_classify_invariant_kept_node_empty_crumb_raises(monkeypatch):
    # Защитный инвариант (точка A3): рассинхрон is_excluded↔build_embedding_input ловится.
    import app.services.estimate_matching_service as svc_mod
    repo = FakeEstimateRepository()
    est = _seed_tree(repo, [("1", "Подготовительные работы", None), ("1.1", "Корпус 8", "1")])
    # Индуцируем рассинхрон: крошка всегда пустая, при этом 1.1 спасается (kept) → инвариант бьёт.
    monkeypatch.setattr(svc_mod, "build_embedding_input", lambda *a, **k: "")
    svc = _classify_svc(repo, classifier=FakeWorkTypeClassifier(default=WorkClass.WORK))
    import pytest
    with pytest.raises(AssertionError):
        svc._classify_nodes(est.id)


def test_classify_collision_gives_different_breadcrumbs() -> None:
    repo = FakeEstimateRepository()
    articles = FakeRepository(candidates=[])
    est = repo.create(
        NewEstimate(user_id=1, filename="f.xlsx", original_object_key="k"),
        [
            EstimateNode("6", "Фасады", None, "СМР", "Фасады", 0, 1),
            EstimateNode("6.1", "навесной типового", "6", None, "x", 1, 2),
            EstimateNode("6.1.1", "подсистема", "6.1", None, "x", 2, 3),
            EstimateNode("6.1", "навесной 1 этажа", "6", None, "x", 3, 2),   # дубль кода 6.1
            EstimateNode("6.1.1", "подсистема", "6.1", None, "x", 4, 3),     # дубль кода 6.1.1
        ],
    )
    svc = _classify_service(repo, articles)
    svc._classify_nodes(est.id)  # noqa: SLF001
    rows = sorted(repo.get(est.id, 1, is_admin=True).rows, key=lambda r: r.source_index)
    # два «6.1.1» (si=2 и si=4) — РАЗНЫЕ крошки (сегодня были бы байт-в-байт одинаковы)
    assert rows[2].embedding_input == "Фасады. навесной типового. подсистема"
    assert rows[4].embedding_input == "Фасады. навесной 1 этажа. подсистема"


def test_match_estimate_logs_summary(caplog) -> None:
    import logging

    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    art = _ready_articles([ArticleCandidate(_article(1, "1.1"), 0.97)])
    with caplog.at_level(logging.INFO, logger="app.services.estimate_matching_service"):
        _service(repo, art).match_estimate(est.id)

    recs = [r for r in caplog.records if hasattr(r, "estimate_id")]
    assert recs, "summary-запись не найдена"
    rec = recs[-1]
    assert rec.estimate_id == est.id
    assert rec.confident == 1
    assert rec.needs_review == 0 and rec.no_match == 0 and rec.match_error == 0
    assert rec.latency_ms >= 0


# ---------------------------------------------------------------------------
# Task 6: _apply_fund — стадия перед арбитром
# ---------------------------------------------------------------------------


def test_apply_fund_hit_writes_matched_fund_and_skips_arbiter() -> None:
    repo, articles = FakeEstimateRepository(), FakeRepository(candidates=[])
    fund = FakeDecisionFundRepository()
    est = repo.create(NewEstimate(1, "f.xlsx", "k"),
                      [EstimateNode("1.1.5", "МОКАП", "1.1", None, "Подг. МОКАП", 0, 3)])
    key = cache_key_hash(normalize_cache_key("Подг. МОКАП"))
    fund.seed_hit(key, CRUMB_DERIVATION_VERSION, FundHit(5, "1.4", "Мокап"))
    svc = _matching_service(repo, articles, fund, apply_fund=True)
    svc._apply_fund(est.id)  # noqa: SLF001
    row = repo.get(est.id, 1, is_admin=True).rows[0]
    assert row.status == "matched_fund" and row.matched_article_id == 5


def test_apply_fund_conflict_and_miss_stay_pending() -> None:
    repo, articles = FakeEstimateRepository(), FakeRepository(candidates=[])
    fund = FakeDecisionFundRepository()
    est = repo.create(NewEstimate(1, "f.xlsx", "k"),
                      [EstimateNode("1.1.5", "МОКАП", "1.1", None, "Подг. МОКАП", 0, 3)])
    key = cache_key_hash(normalize_cache_key("Подг. МОКАП"))
    fund.seed_hit(key, CRUMB_DERIVATION_VERSION, FundHit(5, "1.4", "Мокап"))
    fund.seed_hit(key, CRUMB_DERIVATION_VERSION, FundHit(7, "1.5", "Иное"))  # 2-е живое → конфликт
    svc = _matching_service(repo, articles, fund, apply_fund=True)
    svc._apply_fund(est.id)  # noqa: SLF001
    assert repo.get(est.id, 1, is_admin=True).rows[0].status == "pending"  # конфликт → RAG


def test_apply_fund_disabled_is_noop() -> None:
    repo, articles = FakeEstimateRepository(), FakeRepository(candidates=[])
    fund = FakeDecisionFundRepository()
    est = repo.create(NewEstimate(1, "f.xlsx", "k"),
                      [EstimateNode("1.1.5", "МОКАП", "1.1", None, "Подг. МОКАП", 0, 3)])
    fund.seed_hit(cache_key_hash(normalize_cache_key("Подг. МОКАП")),
                  CRUMB_DERIVATION_VERSION, FundHit(5, "1.4", "Мокап"))
    svc = _matching_service(repo, articles, fund, apply_fund=False)
    svc._apply_fund(est.id)  # noqa: SLF001
    assert repo.get(est.id, 1, is_admin=True).rows[0].status == "pending"  # выключен → не трогает


def test_fund_hit_rows_are_not_embedded() -> None:
    # экономия эмбеддинга — суть кэша (спека §12.2): хит закрывается ДО _embed_nodes
    repo, fund = FakeEstimateRepository(), FakeDecisionFundRepository()
    est = repo.create(NewEstimate(1, "f.xlsx", "k"), [
        EstimateNode("1.1", "МОКАП", "1", None, "МОКАП", 0, 2),
        EstimateNode("1.2", "Кровля", "1", None, "Кровля", 1, 2),
    ])
    fund.seed_hit(cache_key_hash(normalize_cache_key("МОКАП")),
                  CRUMB_DERIVATION_VERSION, FundHit(5, "1.4", "Мокап"))
    art = _ready_articles([ArticleCandidate(_article(9, "1.99"), 0.97)])
    embedder = _Embedder()
    svc = _matching_service(repo, art, fund, apply_fund=True, embedder=embedder)
    svc.match_estimate(est.id)
    embedded = [t for batch in embedder.batches for t in batch]
    assert "МОКАП" not in embedded          # фонд-хит не оплачивал эмбеддинг
    assert "Кровля" in embedded             # промах пошёл штатно
    rows = {r.embedding_input: r for r in repo.get(est.id, 1, is_admin=True).rows}
    assert rows["МОКАП"].status == "matched_fund"
    assert rows["Кровля"].status == "confident"


def test_crumb_version_bump_misses_old_keys() -> None:
    repo, articles = FakeEstimateRepository(), FakeRepository(candidates=[])
    fund = FakeDecisionFundRepository()
    est = repo.create(NewEstimate(1, "f.xlsx", "k"),
                      [EstimateNode("1.1.5", "МОКАП", "1.1", None, "Подг. МОКАП", 0, 3)])
    # запись осела на СТАРОЙ версии (99); лукап идёт на CRUMB_DERIVATION_VERSION → промах
    fund.seed_hit(
        cache_key_hash(normalize_cache_key("Подг. МОКАП")), 99, FundHit(5, "1.4", "Мокап")
    )
    svc = _matching_service(repo, articles, fund, apply_fund=True)
    svc._apply_fund(est.id)  # noqa: SLF001
    assert repo.get(est.id, 1, is_admin=True).rows[0].status == "pending"  # версия не та → холодно
