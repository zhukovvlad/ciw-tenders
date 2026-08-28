"""Тесты `TreeMatchingRunner` — обход чанков сметы, CAS, транзиенты, обрезка (Task 9)."""

from __future__ import annotations

import pytest

from app.domain.entities import (
    EstimateNode,
    EstimateRowStatus,
    NewEstimate,
    SectionMatchResponse,
)
from app.domain.errors import TransientError
from app.domain.tree_matching import estimate_tokens, resolve_parents
from app.services.tree_matching_service import (
    _CONTEXT_SHARE,
    _OUTPUT_MARGIN,
    _SYSTEM_PROMPT_RESERVE,
    CatalogEmptyError,
    CatalogTooLargeError,
    TreeMatchingRunner,
    _max_ancestors_reserve,
)
from tests.fakes import (
    FakeArticleRepository,
    FakeEstimateRepository,
    FakeTreeMatcher,
    make_tree_node,
)

CAT = [
    ("4", "Конструктив"), ("4.2", "Надземная"), ("4.2.1", "Гориз 1-й"), ("4.2.2", "Верт 1-й"),
    ("4.99", "Прочее (конструктив)"), ("9", "Лифты"), ("9.99", "Прочее лифты"),
]


def _articles() -> FakeArticleRepository:
    art = FakeArticleRepository()
    for i, (code, name) in enumerate(CAT, start=1):
        art.add_article(id=i, code=code, name=name)  # parent_id для list_catalog фейка не нужен
    return art


def _node(code: str, name: str, si: int) -> EstimateNode:
    return EstimateNode(code, name, None, "СМР", name, si, code.count(".") + 1)


def _runner(repo, art, matcher, **kw) -> TreeMatchingRunner:
    return TreeMatchingRunner(
        matcher=matcher, estimates=repo, articles=art, chunk_rows=kw.get("chunk_rows", 120),
        min_chunk_rows=10, context_window=200_000, output_reserve_per_row=48,
    )


def by_name(mapping: dict[str, dict]):
    """verdict_fn: имя строки → сырой вердикт (i подставляется по id узла)."""

    def fn(req):
        return [
            {"i": n.id, **mapping[n.name]}
            for n in req.nodes
            if n.id in req.targets and n.name in mapping
        ]

    return fn


def test_happy_path_writes_statuses_and_uses_parent_context_within_chunk() -> None:
    repo, art = FakeEstimateRepository(), _articles()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [
        _node("4", "Конструктив", 0), _node("4.1", "1 Этап", 1), _node("4.1.1", "Гориз 1-й", 2),
        _node("4.1.2", "Прочее", 3), _node("9", "Лифты", 4), _node("9.1", "Прочее", 5)])
    matcher = FakeTreeMatcher(verdict_fn=by_name({
        "Конструктив": {"code": "4", "sure": True, "alt": None},
        "1 Этап": {"code": "org", "sure": True, "alt": None},
        "Гориз 1-й": {"code": "4.2.1", "sure": True, "alt": "4.2.2"},
        "Прочее": {"code": "9.99", "sure": True, "alt": None},
        "Лифты": {"code": "9", "sure": True, "alt": None},
    }))
    counts = _runner(repo, art, matcher).run(est.id)
    rows = {n["name"]: n for n in repo.nodes.values()}
    assert rows["Конструктив"]["status"] == "confident"
    assert rows["1 Этап"]["status"] == "excluded"
    assert rows["Гориз 1-й"]["status"] == "confident"
    assert rows["Гориз 1-й"]["candidates"][1]["code"] == "4.2.2"
    # «Прочее» под «Конструктив» получило 9.99 → вне поддерева доверенного родителя 4 → needs_review
    prochee = [n for n in repo.nodes.values() if n["name"] == "Прочее"]
    assert {n["status"] for n in prochee} == {"needs_review", "confident"}
    assert counts[EstimateRowStatus.CONFIDENT] == 4
    assert len(matcher.requests) == 2  # два корня — два вызова


def test_non_targets_are_context_only_and_not_overwritten() -> None:
    repo, art = FakeEstimateRepository(), _articles()
    est = repo.create(
        NewEstimate(1, "a.xlsx", "k"),
        [_node("4", "Конструктив", 0), _node("4.1", "Гориз 1-й", 1)],
    )
    root = est.rows[0].id
    repo.nodes[root].update(status="confident", matched_code="4", matched_article_id=1)
    matcher = FakeTreeMatcher(verdict_fn=by_name({
        "Конструктив": {"code": "9", "sure": True, "alt": None},
        "Гориз 1-й": {"code": "4.2.1", "sure": True, "alt": None},
    }))
    _runner(repo, art, matcher).run(est.id)
    assert repo.nodes[root]["matched_code"] == "4"  # не перезаписан
    assert matcher.requests[0].targets == {est.rows[1].id}
    assert matcher.requests[0].hints[root] == ("4", True)  # виден как [уже: 4]


def test_parent_chunk_verdict_feeds_child_chunk_context() -> None:
    # лимит 2 строки: корень+первый ребёнок — чанк 1, второй ребёнок — чанк 2
    # с ancestors из свежего дерева
    repo, art = FakeEstimateRepository(), _articles()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [
        _node("4", "Конструктив", 0), _node("4.1", "Гориз 1-й", 1), _node("4.2", "Верт 1-й", 2),
    ])
    matcher = FakeTreeMatcher(verdict_fn=by_name({
        "Конструктив": {"code": "4", "sure": True, "alt": None},
        "Гориз 1-й": {"code": "4.2.1", "sure": True, "alt": None},
        "Верт 1-й": {"code": "9", "sure": True, "alt": None},
    }))
    _runner(repo, art, matcher, chunk_rows=2).run(est.id)
    assert len(matcher.requests) == 2
    assert matcher.requests[1].ancestors[0][1] == ("4", True)  # предок — из чанка 1, доверенный
    assert repo.nodes[est.rows[2].id]["status"] == "needs_review"  # 9 вне поддерева 4 → флаг


def test_transient_marks_remaining_and_descendant_chunks_error() -> None:
    repo, art = FakeEstimateRepository(), _articles()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [
        _node("4", "Конструктив", 0), _node("4.1", "Гориз 1-й", 1),
        _node("4.2", "Верт 1-й", 2), _node("9", "Лифты", 3),
    ])
    repo.nodes[est.rows[1].id]["status"] = "no_match"  # ретрай терминального no_match
    matcher = FakeTreeMatcher(responses=[
        TransientError("boom"),
        SectionMatchResponse(
            items=[{"i": est.rows[3].id, "code": "9", "sure": True, "alt": None}],
            truncated=False,
        ),
    ])
    counts = _runner(repo, art, matcher, chunk_rows=2).run(est.id)
    st = {n["name"]: n for n in repo.nodes.values()}
    assert st["Конструктив"]["status"] == "error"
    assert st["Конструктив"]["match_error"].startswith("tree_transient")
    assert st["Гориз 1-й"]["status"] == "error"  # no_match не остался терминальным
    assert st["Верт 1-й"]["match_error"] == "tree_ancestor_failed"  # дочерний чанк упавшего дерева
    assert st["Лифты"]["status"] == "confident"  # сиблинг-раздел не пострадал
    assert counts[EstimateRowStatus.ERROR] == 3


def test_truncated_response_splits_chunk_then_errors_below_min() -> None:
    # Fix round 1 / finding 1: half считается от РЕАЛЬНОГО размера чанка
    # (min(max_rows, len(chunk.indices)) // 2), а не от конфигурационного chunk_rows.
    # Для чанка из 3 строк это ВСЕГДА даёт half=1 (3 // 2), независимо от chunk_rows —
    # поэтому настоящий сплит здесь распадается на 3 отдельных однострочных чанка
    # (не на «[корень+первый ребёнок], [второй]», как было при старой формуле
    # `chunk_rows // 2`, — см. Fix round 1 в отчёте).
    repo, art = FakeEstimateRepository(), _articles()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [
        _node("4", "Конструктив", 0), _node("4.1", "Гориз 1-й", 1), _node("4.2", "Верт 1-й", 2),
    ])

    def ok(ids):
        return SectionMatchResponse(
            items=[{"i": i, "code": "4", "sure": True, "alt": None} for i in ids],
            truncated=False,
        )

    trunc = SectionMatchResponse(items=[], truncated=True)
    r0, r1, r2 = (r.id for r in est.rows)
    matcher = FakeTreeMatcher(responses=[trunc, ok([r0]), ok([r1]), ok([r2])])
    # min_chunk_rows=1: half=3//2=1 не ниже минимума → реальный сплит на 3 листа
    runner = TreeMatchingRunner(
        matcher=matcher, estimates=repo, articles=art, chunk_rows=4, min_chunk_rows=1,
        context_window=200_000, output_reserve_per_row=48,
    )
    runner.run(est.id)
    assert len(matcher.requests) == 4
    assert all(n["status"] == "confident" for n in repo.nodes.values())
    assert [sorted(n.id for n in r.nodes) for r in matcher.requests] == [
        [r0, r1, r2], [r0], [r1], [r2],
    ]
    # ниже минимума → error (не затронуто фиксом: чанк уже из 1 строки при первой обрезке)
    repo2, matcher2 = FakeEstimateRepository(), FakeTreeMatcher(responses=[trunc])
    est2 = repo2.create(NewEstimate(1, "a.xlsx", "k"), [_node("4", "Конструктив", 0)])
    TreeMatchingRunner(
        matcher=matcher2, estimates=repo2, articles=art, chunk_rows=10, min_chunk_rows=10,
        context_window=200_000, output_reserve_per_row=48,
    ).run(est2.id)
    assert repo2.nodes[est2.rows[0].id]["match_error"] == "tree_output_truncated"


def test_oversized_row_commits_row_too_large_without_calling_matcher() -> None:
    # Finding 2: ветка chunk.oversized ничем не была закрыта. Узел, чья собственная
    # стоимость строки превышает бюджет чанка, должен стать отдельным чанком с
    # oversized=[себя], закоммититься error/tree_row_too_large и НЕ попасть в вызов
    # матчера (иначе повторный commit по «отсутствующему» вердикту тихо перезаписал бы
    # причину на tree_missing_verdict).
    repo, art = FakeEstimateRepository(), _articles()
    nodes = [_node("4", "Конструктив", 0), _node("4.1", "x" * 260, 1)]
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), nodes)
    root_id, child_id = (r.id for r in est.rows)
    matcher = FakeTreeMatcher(
        verdict_fn=by_name({"Конструктив": {"code": "4", "sure": True, "alt": None}})
    )
    # окно подобрано так, что row_budget=100 (root cost ~25 влезает, имя ребёнка в 260 символов
    # даёт row_cost ~108 > 100 — узел "не влезает" сам по себе), с учётом ФАКТИЧЕСКОГО
    # ancestors_reserve этого дерева (P2-1: больше не фиксированная 600 — считаем её так же, как
    # run()) и фактического catalog_tokens справочника фикстуры.
    catalog_tokens = sum(
        estimate_tokens("  " * a.code.count(".") + f"({a.code}) {a.name}")
        for a in art.list_catalog()
    )
    shadow_tree = [make_tree_node(i, n.depth, n.code, n.name) for i, n in enumerate(nodes)]
    ancestors_reserve = _max_ancestors_reserve(
        shadow_tree, resolve_parents(shadow_tree), art.list_catalog()
    )
    window = int((1_500 + catalog_tokens + ancestors_reserve + 512 + 100) / 0.8)
    runner = TreeMatchingRunner(
        matcher=matcher, estimates=repo, articles=art, chunk_rows=120, min_chunk_rows=1,
        context_window=window, output_reserve_per_row=10,
    )
    runner.run(est.id)
    assert repo.nodes[root_id]["status"] == "confident"
    assert repo.nodes[child_id]["status"] == "error"
    assert repo.nodes[child_id]["match_error"] == "tree_row_too_large"
    # матчер вызван только для чанка корня — чанк переростка вернулся до вызова матчера
    assert len(matcher.requests) == 1
    assert matcher.requests[0].targets == {root_id}


def test_nested_truncation_genuinely_shrinks_chunk_not_reissues() -> None:
    # Finding 1/4: half считается от РЕАЛЬНОГО размера текущего чанка
    # (min(max_rows, len(chunk.indices)) // 2), а не от конфигурационного chunk_rows.
    # Дерево из 2 строк, chunk_rows=8 (много больше фактического размера чанка) —
    # ровно тот перекос, из-за которого старая формула была бы «инертной».
    repo, art = FakeEstimateRepository(), _articles()
    est = repo.create(
        NewEstimate(1, "a.xlsx", "k"),
        [_node("4", "Конструктив", 0), _node("4.1", "Гориз 1-й", 1)],
    )
    r0, r1 = (r.id for r in est.rows)
    trunc = SectionMatchResponse(items=[], truncated=True)

    def ok(ids):
        return SectionMatchResponse(
            items=[{"i": i, "code": "4", "sure": True, "alt": None} for i in ids],
            truncated=False,
        )

    matcher = FakeTreeMatcher(responses=[trunc, trunc, ok([r1])])
    runner = TreeMatchingRunner(
        matcher=matcher, estimates=repo, articles=art, chunk_rows=8, min_chunk_rows=1,
        context_window=200_000, output_reserve_per_row=48,
    )
    runner.run(est.id)
    seen = [frozenset(n.id for n in r.nodes) for r in matcher.requests]
    # ровно 3 вызова, и НИ ОДИН не повторяет узловой набор предыдущего — половинка от
    # РЕАЛЬНОГО размера (2 // 2 = 1) сразу даёт настоящий сплит на 2 листа, а не то же
    # самое требование ещё раз (под старой формулой `chunk_rows // 2 = 8 // 2 = 4`
    # split_sections(max_rows=4) вернул бы тот же неразделённый 2-узловый чанк, потому
    # что 2 <= 4 — тождественный повторный запрос; см. Fix round 1 в отчёте).
    assert len(matcher.requests) == 3
    assert len(seen) == len(set(seen))
    assert seen == [frozenset({r0, r1}), frozenset({r0}), frozenset({r1})]
    # корень — однострочный чанк, обрезка на нём уже ниже пола (half=1//2=0) → error сразу
    assert repo.nodes[r0]["status"] == "error"
    assert repo.nodes[r0]["match_error"] == "tree_output_truncated"
    assert repo.nodes[r1]["status"] == "confident"


def test_catalog_over_quarter_of_window_raises_before_row_budget() -> None:
    # Finding 5, первая точка raise (:90-93): справочник > 25% окна — режется до того,
    # как вообще считается row_budget.
    repo, art = FakeEstimateRepository(), _articles()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("4", "Конструктив", 0)])
    runner = TreeMatchingRunner(
        matcher=FakeTreeMatcher(responses=[]), estimates=repo, articles=art,
        chunk_rows=120, min_chunk_rows=1, context_window=100, output_reserve_per_row=48,
    )
    with pytest.raises(CatalogTooLargeError) as exc:
        runner.run(est.id)
    assert "25%" in str(exc.value)


def test_row_budget_non_positive_after_reserves_raises() -> None:
    # Finding 5, вторая точка raise (:107-110): справочник проходит первую проверку
    # (<=25% окна), но после вычета системных резервов бюджет строк уходит в ноль/минус.
    repo, art = FakeEstimateRepository(), _articles()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("4", "Конструктив", 0)])
    runner = TreeMatchingRunner(
        matcher=FakeTreeMatcher(responses=[]), estimates=repo, articles=art,
        chunk_rows=120, min_chunk_rows=1, context_window=1000, output_reserve_per_row=48,
    )
    with pytest.raises(CatalogTooLargeError) as exc:
        runner.run(est.id)
    assert "не остаётся бюджета" in str(exc.value)


def test_ancestors_ordered_root_first_for_deep_chunk() -> None:
    # Finding 6: `_ancestors` строит путь снизу вверх и разворачивает в конце —
    # единственный существующий assert брал чанк с предком длины 1, где reversed —
    # no-op. Трёхуровневая цепочка ловит инверсию, если её кто-то уберёт.
    repo, art = FakeEstimateRepository(), _articles()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [
        _node("4", "Root", 0), _node("4.1", "Mid", 1), _node("4.1.1", "Leaf", 2),
    ])
    matcher = FakeTreeMatcher(verdict_fn=by_name({
        "Root": {"code": "4", "sure": True, "alt": None},
        "Mid": {"code": "4", "sure": True, "alt": None},
        "Leaf": {"code": "4", "sure": True, "alt": None},
    }))
    # chunk_rows=1: каждый узел — отдельный чанк, обрабатываются сверху вниз, так что к
    # моменту чанка «Leaf» оба предка уже закоммичены и видны в req.ancestors
    _runner(repo, art, matcher, chunk_rows=1).run(est.id)
    leaf_req = matcher.requests[-1]
    assert [n.code for n, _ in leaf_req.ancestors] == ["4", "4.1"]


def test_lost_cas_refreshes_parent_before_children() -> None:
    repo, art = FakeEstimateRepository(), _articles()
    est = repo.create(
        NewEstimate(1, "a.xlsx", "k"),
        [_node("4", "Конструктив", 0), _node("4.1", "Гориз 1-й", 1)],
    )
    root, child = (r.id for r in est.rows)

    def fn(req):
        # «оператор» успевает переопределить корень между вызовом и записью
        repo.save_review_decision(
            root, review_status="overridden", final_article_id=6,
            final_code="9", final_name="Лифты",
        )
        return [
            {"i": root, "code": "4", "sure": True, "alt": None},
            {"i": child, "code": "4.2.1", "sure": True, "alt": None},
        ]

    counts = _runner(repo, art, FakeTreeMatcher(verdict_fn=fn)).run(est.id)
    assert repo.nodes[root]["final_code"] == "9"  # ревью не затёрто
    assert repo.nodes[child]["status"] == "needs_review"  # 4.2.1 вне поддерева свежего 9
    # Fix round 1 / finding 3: проигранный CAS корня не должен попасть в счётчики —
    # засчитан только успешный CAS ребёнка.
    assert sum(counts.values()) == 1
    assert counts[EstimateRowStatus.NEEDS_REVIEW] == 1


def test_ancestors_reserve_grows_with_deeper_or_longer_named_chain() -> None:
    # P2-1: _ANCESTORS_RESERVE был фиксированной константой (600) — теперь это фактический
    # худший случай по дереву (см. tree_prompt.render_ancestors), так что глубокая цепочка с
    # длинными именами должна давать БОЛЬШИЙ резерв, чем неглубокая с короткими — то есть член
    # больше не константа.
    catalog = _articles().list_catalog()
    shallow = [make_tree_node(1, 1, "4", "A"), make_tree_node(2, 2, "4.1", "B")]
    deep = [
        make_tree_node(1, 1, "4", "x" * 40),
        make_tree_node(2, 2, "4.1", "x" * 40),
        make_tree_node(3, 3, "4.1.1", "x" * 40),
        make_tree_node(4, 4, "4.1.1.1", "x" * 40),
        make_tree_node(5, 5, "4.1.1.1.1", "x" * 40),
        make_tree_node(6, 6, "4.1.1.1.1.1", "x" * 40),
    ]
    shallow_reserve = _max_ancestors_reserve(shallow, resolve_parents(shallow), catalog)
    deep_reserve = _max_ancestors_reserve(deep, resolve_parents(deep), catalog)
    # инвариант §5.2 — вычитаемое растёт вместе с реальной глубиной/длиной пути предков, а не
    # остаётся одной и той же константой (600) независимо от формы дерева
    assert deep_reserve > shallow_reserve
    assert deep_reserve - shallow_reserve > 100  # разница ощутима, не шум округления


def test_budget_respects_window_and_shrinks_with_output_reserve() -> None:
    # 10 узлов-сиблингов под корнем, имена по 30 символов (~10 токенов + 8 формат + reserve).
    repo, art = FakeEstimateRepository(), _articles()
    nodes = [_node("4", "Конструктив", 0)] + [_node(f"4.{k}", "x" * 30, k) for k in range(1, 11)]

    # ancestors_reserve не зависит от id узлов (только код/имя/глубина) — считаем его ТОЙ ЖЕ
    # функцией, что и run(), на «теневом» дереве такой же формы, ДО выбора окна.
    catalog_tokens = sum(
        estimate_tokens("  " * a.code.count(".") + f"({a.code}) {a.name}")
        for a in art.list_catalog()
    )
    shadow_tree = [make_tree_node(i, n.depth, n.code, n.name) for i, n in enumerate(nodes)]
    ancestors_reserve = _max_ancestors_reserve(
        shadow_tree, resolve_parents(shadow_tree), art.list_catalog()
    )

    est = repo.create(NewEstimate(1, "a.xlsx", "k"), nodes)

    def fn(req):
        return [
            {"i": n.id, "code": "4", "sure": True, "alt": None}
            for n in req.nodes
            if n.id in req.targets
        ]

    # каталог ~7 статей (~60 токенов); окно подобрано так, что бюджет строк ≈ 300 токенов
    window = int((1_500 + catalog_tokens + ancestors_reserve + 512 + 300) / 0.8)
    m1 = FakeTreeMatcher(verdict_fn=fn)
    TreeMatchingRunner(
        matcher=m1, estimates=repo, articles=art, chunk_rows=120, min_chunk_rows=1,
        context_window=window, output_reserve_per_row=1,
    ).run(est.id)
    est2 = repo.create(NewEstimate(1, "b.xlsx", "k"), nodes)
    m2 = FakeTreeMatcher(verdict_fn=fn)
    TreeMatchingRunner(
        matcher=m2, estimates=repo, articles=art, chunk_rows=120, min_chunk_rows=1,
        context_window=window, output_reserve_per_row=40,
    ).run(est2.id)
    # row_budget пересчитан ровно так, как это делает run() — включая индентированный catalog_tokens
    row_budget = (
        int(_CONTEXT_SHARE * window)
        - _SYSTEM_PROMPT_RESERVE - catalog_tokens - ancestors_reserve - _OUTPUT_MARGIN
    )
    # инвариант: каждый чанк укладывается в бюджет с учётом резерва ответа
    for m, reserve in ((m1, 1), (m2, 40)):
        for req in m.requests:
            cost = sum(
                estimate_tokens(f"{n.id} | {n.code} | {n.name}") + 8 + reserve
                for n in req.nodes
            )
            assert cost <= row_budget
    # больший резерв ответа → чанки мельче → вызовов больше
    assert len(m2.requests) > len(m1.requests) >= 1
    assert all(n["status"] == "confident" for n in repo.nodes.values())
    # прижимка Task 8: один и тот же каталог (объект/порядок) передаётся во все чанки — иначе
    # тихо ломается prompt-cache без падения ни одного другого теста.
    for m in (m1, m2):
        first_catalog = m.requests[0].catalog
        for req in m.requests:
            assert req.catalog is first_catalog or req.catalog == first_catalog


def test_empty_catalog_raises() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("4", "Конструктив", 0)])
    with pytest.raises(CatalogEmptyError):
        _runner(repo, FakeArticleRepository(), FakeTreeMatcher(responses=[])).run(est.id)


def test_fund_enabled_not_implemented_in_pr1() -> None:
    with pytest.raises(NotImplementedError):
        TreeMatchingRunner(
            matcher=FakeTreeMatcher(responses=[]), estimates=FakeEstimateRepository(),
            articles=_articles(), chunk_rows=1, min_chunk_rows=1, context_window=1,
            output_reserve_per_row=1, fund_enabled=True,
        )
