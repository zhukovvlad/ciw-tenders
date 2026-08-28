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
from app.domain.tree_matching import estimate_tokens
from app.services.tree_matching_service import (
    _ANCESTORS_RESERVE,
    _CONTEXT_SHARE,
    _OUTPUT_MARGIN,
    _SYSTEM_PROMPT_RESERVE,
    CatalogEmptyError,
    TreeMatchingRunner,
)
from tests.fakes import FakeArticleRepository, FakeEstimateRepository, FakeTreeMatcher

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
    matcher = FakeTreeMatcher(responses=[trunc, ok([r0, r1]), ok([r2])])
    # chunk_rows=4: первый вызов — все 3 строки; обрезка → half=2 →
    # чанки [корень+первый ребёнок], [второй]
    runner = TreeMatchingRunner(
        matcher=matcher, estimates=repo, articles=art, chunk_rows=4, min_chunk_rows=2,
        context_window=200_000, output_reserve_per_row=48,
    )
    runner.run(est.id)
    assert len(matcher.requests) == 3
    assert all(n["status"] == "confident" for n in repo.nodes.values())
    assert [sorted(n.id for n in r.nodes) for r in matcher.requests] == [
        [r0, r1, r2], [r0, r1], [r2],
    ]
    # ниже минимума → error
    repo2, matcher2 = FakeEstimateRepository(), FakeTreeMatcher(responses=[trunc])
    est2 = repo2.create(NewEstimate(1, "a.xlsx", "k"), [_node("4", "Конструктив", 0)])
    TreeMatchingRunner(
        matcher=matcher2, estimates=repo2, articles=art, chunk_rows=10, min_chunk_rows=10,
        context_window=200_000, output_reserve_per_row=48,
    ).run(est2.id)
    assert repo2.nodes[est2.rows[0].id]["match_error"] == "tree_output_truncated"


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

    _runner(repo, art, FakeTreeMatcher(verdict_fn=fn)).run(est.id)
    assert repo.nodes[root]["final_code"] == "9"  # ревью не затёрто
    assert repo.nodes[child]["status"] == "needs_review"  # 4.2.1 вне поддерева свежего 9


def test_budget_respects_window_and_shrinks_with_output_reserve() -> None:
    # 10 узлов-сиблингов под корнем, имена по 30 символов (~10 токенов + 8 формат + reserve).
    repo, art = FakeEstimateRepository(), _articles()
    nodes = [_node("4", "Конструктив", 0)] + [_node(f"4.{k}", "x" * 30, k) for k in range(1, 11)]
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), nodes)

    def fn(req):
        return [
            {"i": n.id, "code": "4", "sure": True, "alt": None}
            for n in req.nodes
            if n.id in req.targets
        ]

    # каталог ~7 статей (~60 токенов); окно подобрано так, что бюджет строк ≈ 300 токенов
    window = int((1_500 + 60 + 600 + 512 + 300) / 0.8)
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
    catalog_tokens = sum(
        estimate_tokens("  " * a.code.count(".") + f"({a.code}) {a.name}")
        for a in art.list_catalog()
    )
    row_budget = (
        int(_CONTEXT_SHARE * window)
        - _SYSTEM_PROMPT_RESERVE - catalog_tokens - _ANCESTORS_RESERVE - _OUTPUT_MARGIN
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
