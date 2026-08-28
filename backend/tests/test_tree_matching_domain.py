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
    F_INCONSISTENT,
    F_MISSING,
    F_OUTSIDE_PARENT,
    F_UNKNOWN_CODE,
    Chunk,
    build_hints,
    effective_ancestor_context,
    estimate_tokens,
    neighbors,
    resolve_parents,
    split_sections,
    to_node_match,
    validate_one,
    validate_verdicts,
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


def test_context_rejected_needs_review_ancestor_is_transparent() -> None:
    # needs_review-предок, но оператор его отклонил (review_status="rejected" — «статьи нет»,
    # решение, а не неуверенность): барьер НЕ должен взводиться — rejected прозрачен, как
    # excluded/no_match/error/pending (спека §3.3, таблица, строка 4), и как уже делает hint_for.
    nodes = [
        _tn(1, 1, "1", status="needs_review", review_status="rejected"),
        _tn(2, 2, "1.1"),
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


CAT = {c.code: c for c in [
    CatalogArticle(1, "4", "Конструктив", None), CatalogArticle(2, "4.2", "Надземная", "4"),
    CatalogArticle(3, "4.2.1", "Гориз 1-й", "4.2"), CatalogArticle(4, "4.2.2", "Верт 1-й", "4.2"),
    CatalogArticle(5, "4.2.3", "Гориз проч", "4.2"), CatalogArticle(6, "9", "Лифты", None),
]}
TRUSTED = AncestorContext("4.2", False)
ROOT = AncestorContext(None, False)
BARRIER = AncestorContext("4.2", True)


def test_hint_for_trust_rules() -> None:
    from app.domain.tree_matching import hint_for
    assert hint_for(_tn(1, 1, "4", status="confident", matched_code="4")) == ("4", True)
    assert hint_for(_tn(
        1, 1, "4", status="needs_review", matched_code="4",
        review_status="overridden", final_code="5", final_article_id=5,
    )) == ("5", True)
    assert hint_for(_tn(1, 1, "4", status="needs_review", matched_code="4")) == ("4", False)
    # confident, но оператор отверг → старый код НЕ показывать как [уже: …]
    assert hint_for(_tn(
        1, 1, "4", status="confident", matched_code="4", review_status="rejected",
    )) is None
    for st in ("excluded", "no_match", "error", "pending"):
        assert hint_for(_tn(1, 1, "4", status=st, matched_code="4")) is None


def test_build_hints_only_for_non_targets() -> None:
    nodes = [_tn(1, 1, "4", status="confident", matched_code="4"),
             _tn(2, 2, "4.1", status="needs_review", matched_code="4.2"),
             _tn(3, 3, "4.1.1", status="excluded"), _tn(4, 3, "4.1.2")]
    assert build_hints([0, 1, 2, 3], nodes, targets={4}) == {1: ("4", True), 2: ("4.2", False)}


def test_validate_flags() -> None:
    codes = set(CAT)
    ok = {"i": 1, "code": "4.2.1", "sure": True, "alt": "4.2.3"}
    unknown = {"i": 1, "code": "77", "sure": True, "alt": None}
    no_code = {"i": 1, "code": None, "sure": True, "alt": None}
    org_with_code = {"i": 1, "code": "4.2.1", "sure": True, "alt": None, "kind": "org"}
    outside = {"i": 1, "code": "9", "sure": True, "alt": None}
    rollup_up = {"i": 1, "code": "4", "sure": True, "alt": None}
    malformed = {"i": 1, "code": "4.2.1", "sure": "yes", "alt": "4.2.1"}
    assert validate_one(ok, 1, codes, TRUSTED)[1] == ()
    assert F_UNKNOWN_CODE in validate_one(unknown, 1, codes, TRUSTED)[1]
    assert F_INCONSISTENT in validate_one(no_code, 1, codes, TRUSTED)[1]
    assert F_INCONSISTENT in validate_one(org_with_code, 1, codes, TRUSTED)[1]
    assert F_OUTSIDE_PARENT in validate_one(outside, 1, codes, TRUSTED)[1]
    assert validate_one(outside, 1, codes, ROOT)[1] == ()  # корень: нет проверки
    assert validate_one(rollup_up, 1, codes, TRUSTED)[1] == ()  # роллап вверх допустим
    assert validate_one(None, 1, codes, TRUSTED) == (None, (F_MISSING,))
    _, flags = validate_one(malformed, 1, codes, TRUSTED)
    assert "malformed" in flags


def test_validate_many_ignores_foreign_and_duplicates() -> None:
    raw = [{"i": 9, "code": "4", "sure": True}, {"i": 1, "code": "4.2.1", "sure": True},
           {"i": 1, "code": "4.2.2", "sure": True}]
    out = validate_verdicts(raw, targets={1, 2}, catalog_codes=set(CAT), ctx_of=lambda i: TRUSTED)
    assert out[1][0].article_code == "4.2.1" and out[2] == (None, (F_MISSING,))
    assert 9 not in out


def test_to_node_match_matrix() -> None:
    codes = set(CAT)
    ok = validate_one({"i": 1, "code": "4.2.1", "sure": True, "alt": "4.2.3"}, 1, codes, TRUSTED)
    m = to_node_match(ok, TRUSTED, CAT)
    assert m.status == "confident" and m.matched_code == "4.2.1" and m.matched_id == 3
    assert [c.code for c in m.candidates][:2] == ["4.2.1", "4.2.3"]
    assert all(c.score is None for c in m.candidates)
    assert to_node_match(ok, BARRIER, CAT).status == "needs_review"  # барьер гасит sure
    unsure = validate_one({"i": 1, "code": "4.2.1", "sure": False, "alt": None}, 1, codes, TRUSTED)
    assert to_node_match(unsure, TRUSTED, CAT).status == "needs_review"
    # sure=True, код в каталоге, но вне доверенного поддерева (outside_parent) —
    # флаг всё равно должен погасить confident: geometry-нарушение не должно уходить
    # оператору как подтверждённое, код при этом сохраняется для ревью.
    outside = validate_one({"i": 1, "code": "9", "sure": True, "alt": None}, 1, codes, TRUSTED)
    assert outside[1] == (F_OUTSIDE_PARENT,)
    m_outside = to_node_match(outside, TRUSTED, CAT)
    assert m_outside.status == "needs_review" and m_outside.matched_code == "9"
    org = validate_one({"i": 1, "code": "org", "sure": True, "alt": None}, 1, codes, TRUSTED)
    assert to_node_match(org, TRUSTED, CAT).status == "excluded"
    none = validate_one({"i": 1, "code": "none", "sure": True, "alt": None}, 1, codes, TRUSTED)
    assert to_node_match(none, TRUSTED, CAT).status == "no_match"
    unk = validate_one({"i": 1, "code": "77", "sure": True, "alt": None}, 1, codes, TRUSTED)
    m = to_node_match(unk, TRUSTED, CAT)
    assert m.status == "needs_review" and m.matched_code is None
    # дети trusted + сама
    assert {c.code for c in m.candidates} == {"4.2", "4.2.1", "4.2.2", "4.2.3"}
    miss = to_node_match((None, (F_MISSING,)), TRUSTED, CAT)
    assert miss.status == "error" and miss.match_error == "tree_missing_verdict"


def test_neighbors_order_and_limit() -> None:
    c = neighbors(CAT, "4.2.1", "4.2.3", limit=5)
    # выбранная, альт, сёстры, родитель
    assert [x.code for x in c] == ["4.2.1", "4.2.3", "4.2.2", "4.2"]
