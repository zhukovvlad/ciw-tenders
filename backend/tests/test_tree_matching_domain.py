"""Тесты сущностей tree-движка (доменный слой)."""

from __future__ import annotations

from app.domain.decision_fund import FUND_KEY_VERSION, fund_key_v3
from app.domain.entities import (
    AncestorContext,
    CatalogArticle,
    MatchCandidate,
    NodeVerdict,
    SectionMatchRequest,
    TreeNode,
)
from app.domain.tree_matching import (
    Chunk,
    effective_ancestor_context,
    estimate_tokens,
    resolve_parents,
    split_sections,
)
from tests.fakes import make_tree_node as _tn


def _tok(n: TreeNode) -> int:
    return 1


def _chain(depths: list[int]) -> list[TreeNode]:
    return [_tn(i + 1, d, ".".join(["1"] * d)) for i, d in enumerate(depths)]


def test_tree_entities_construct() -> None:
    n = _tn(1, 1, "1")
    ctx = AncestorContext(trusted_code=None, has_uncertain_barrier=False)
    v = NodeVerdict(node_id=1, kind="article", article_code="1", sure=True, alt_code=None)
    req = SectionMatchRequest(
        nodes=[n], ancestors=[], hints={}, targets=frozenset({1}),
        catalog=[CatalogArticle(1, "1", "Раздел", None)], precedents=[])
    assert req.targets == {1} and v.kind == "article" and ctx.trusted_code is None


def test_match_candidate_score_nullable() -> None:
    assert MatchCandidate(id=1, code="1", name="x", score=None).score is None


def test_resolve_parents_positional_not_by_code() -> None:
    # коды повторяются между этапами: второй «6.2» — ребёнок второго «6», не первого
    nodes = [
        _tn(1, 1, "6"), _tn(2, 2, "6.2"), _tn(3, 1, "6"), _tn(4, 2, "6.2"), _tn(5, 4, "6.2.1.1"),
    ]
    assert resolve_parents(nodes) == [None, 0, None, 2, 3]  # скачок глубины 2→4: ближайший открытый


def test_context_trusted_stops_at_reviewed_or_confident() -> None:
    nodes = [
        _tn(1, 1, "4", status="confident", matched_code="4"),
        _tn(2, 2, "4.1", status="needs_review", matched_code="4.9"),
        _tn(3, 3, "4.1.1"),
    ]
    p = resolve_parents(nodes)
    # A→B(needs_review)→C
    assert effective_ancestor_context(2, nodes, p) == AncestorContext("4", True)
    nodes2 = [_tn(1, 1, "4", status="needs_review", matched_code="4",
                  review_status="overridden", final_code="5"), _tn(2, 2, "4.1")]
    ctx2 = effective_ancestor_context(1, nodes2, resolve_parents(nodes2))
    assert ctx2 == AncestorContext("5", False)


def test_context_rejected_confident_ancestor_is_transparent() -> None:
    # confident-предок, но оператор отклонил (review_status="rejected" — «статьи нет»):
    # matched_code не должен просочиться потомку как доверенный контекст
    nodes = [
        _tn(1, 1, "4", status="confident", matched_code="4", review_status="rejected"),
        _tn(2, 2, "4.1"),
    ]
    p = resolve_parents(nodes)
    assert effective_ancestor_context(1, nodes, p) == AncestorContext(None, False)


def test_context_barrier_with_no_trusted_ancestor() -> None:
    # needs_review-корень без доверенного предка выше: барьер взведён, код отсутствует —
    # именно это состояние гасит fund_key_v3 (спека §6.1) на самой частой форме сомнительной цепочки
    nodes = [_tn(1, 1, "1", status="needs_review"), _tn(2, 2, "1.1")]
    p = resolve_parents(nodes)
    assert effective_ancestor_context(1, nodes, p) == AncestorContext(None, True)


def test_context_transparent_statuses_and_root() -> None:
    nodes = [
        _tn(1, 1, "1", status="excluded"), _tn(2, 2, "1.1", status="no_match"), _tn(3, 3, "1.1.1"),
    ]
    p = resolve_parents(nodes)
    # корень — доверенная база
    assert effective_ancestor_context(2, nodes, p) == AncestorContext(None, False)
    assert effective_ancestor_context(0, nodes, p) == AncestorContext(None, False)


def test_fund_key_v3_uses_trusted_code_and_none_on_barrier() -> None:
    n = _tn(1, 2, "1.1", name="  Прочее ")
    assert fund_key_v3(n, AncestorContext("4.2", False)) == "прочее\x1f4.2"
    assert fund_key_v3(n, AncestorContext(None, False)) == "прочее\x1f"
    assert fund_key_v3(n, AncestorContext("4.2", True)) is None
    assert FUND_KEY_VERSION == 3


def test_estimate_tokens_ceil_div_3() -> None:
    assert estimate_tokens("") == 0 and estimate_tokens("ab") == 1 and estimate_tokens("abcd") == 2


def test_split_small_section_is_one_chunk() -> None:
    nodes = _chain([1, 2, 2, 3])
    chunks = split_sections(
        nodes, resolve_parents(nodes), max_rows=10, budget_tokens=100, row_tokens=_tok
    )
    assert chunks == [Chunk(root=0, indices=[0, 1, 2, 3], oversized=[])]


def test_split_by_children_keeps_parent_chunk_first() -> None:
    # корень + два ребёнка по 3 узла; лимит 4 → шапка = корень + первый ребёнок, второй — отдельно
    nodes = _chain([1, 2, 3, 3, 2, 3, 3])
    chunks = split_sections(
        nodes, resolve_parents(nodes), max_rows=4, budget_tokens=100, row_tokens=_tok
    )
    assert [c.indices for c in chunks] == [[0, 1, 2, 3], [4, 5, 6]]
    assert chunks[1].root == 4


def test_split_single_oversized_child_recurses_and_terminates() -> None:
    # цепочка без сиблингов глубже лимита: каждый уровень становится чанком-звеном
    nodes = _chain([1, 2, 3, 4, 5])
    chunks = split_sections(
        nodes, resolve_parents(nodes), max_rows=2, budget_tokens=100, row_tokens=_tok
    )
    assert [c.indices for c in chunks] == [[0], [1], [2], [3, 4]]


def test_split_token_budget_and_row_too_large() -> None:
    nodes = _chain([1, 2, 2])
    big = {2: 50}  # _chain: id = индекс + 1 → второй узел (индекс 1)
    chunks = split_sections(
        nodes,
        resolve_parents(nodes),
        max_rows=10,
        budget_tokens=20,
        row_tokens=lambda n: big.get(n.id, 1),
    )
    assert chunks[0].indices == [0] and chunks[1].oversized == [1] and chunks[1].indices == [1]
    assert chunks[2].indices == [2]
