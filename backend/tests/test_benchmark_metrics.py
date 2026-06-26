from __future__ import annotations

from app.domain.benchmark import BenchmarkKind, NodeOutcome, compute_metrics


def _m(**kw) -> NodeOutcome:
    base = {
        "expected_kind": BenchmarkKind.MATCHABLE,
        "expected_code": "1.1",
        "kept": True,
        "status": "confident",
        "matched_code": "1.1",
        "top3_codes": ["1.1", "1.2", "1.3"],
        "catalog_has_code": True,
        "catalog_name_norm": None,
    }
    base.update(kw)
    return NodeOutcome(**base)


def test_group_a_matrix_counts_structural_and_matchable_only():
    outcomes = [
        _m(
            expected_kind=BenchmarkKind.STRUCTURAL,
            expected_code=None,
            kept=False,
            status="excluded",
        ),
        _m(
            expected_kind=BenchmarkKind.STRUCTURAL,
            expected_code=None,
            kept=True,
            status="no_match",
        ),
        _m(kept=False, status="excluded"),  # matchable, исключён → FN
        _m(),  # matchable, оставлен → TP
        _m(
            expected_kind=BenchmarkKind.NO_ARTICLE,
            expected_code=None,
            kept=True,
            status="no_match",
        ),
    ]
    r = compute_metrics(outcomes)
    # no_article НЕ в матрице
    assert (r.a_tn, r.a_fp, r.a_fn, r.a_tp) == (1, 1, 1, 1)


def test_group_a_prime_no_article_split_is_exhaustive():
    outcomes = [
        _m(
            expected_kind=BenchmarkKind.NO_ARTICLE,
            expected_code=None,
            kept=True,
            status="no_match",
        ),
        _m(
            expected_kind=BenchmarkKind.NO_ARTICLE,
            expected_code=None,
            kept=True,
            status="confident",
            matched_code="9.9",
        ),
        _m(
            expected_kind=BenchmarkKind.NO_ARTICLE,
            expected_code=None,
            kept=True,
            status="needs_review",
            matched_code="9.9",
        ),
    ]
    r = compute_metrics(outcomes)
    assert r.no_article_total == 3
    assert r.no_article_correct_no_match == 1
    assert r.no_article_wrong_confident == 1
    assert r.no_article_needs_review == 1
    # бакеты исчерпывающие: сумма реконсилится с total
    assert (
        r.no_article_correct_no_match
        + r.no_article_wrong_confident
        + r.no_article_needs_review
    ) == r.no_article_total


def test_error_status_excluded_from_b_denominator():
    outcomes = [
        _m(status="error", matched_code=None, top3_codes=[]),  # транзиентная AI-ошибка
        _m(matched_code="1.1", top3_codes=["1.1"]),
    ]
    r = compute_metrics(outcomes)
    assert r.b_error == 1
    assert r.b_total == 1  # error НЕ в знаменателе top-1/top-3
    assert r.b_top1_hits == 1


def test_group_b_top1_top3_only_matchable_kept():
    outcomes = [
        _m(matched_code="1.1", top3_codes=["1.1", "2.2"]),          # top1 hit, top3 hit
        _m(matched_code="9.9", top3_codes=["1.1", "9.9", "3.3"]),   # top1 miss, top3 hit
        _m(matched_code="9.9", top3_codes=["8.8", "9.9", "3.3"]),   # top1 miss, top3 miss
    ]
    r = compute_metrics(outcomes)
    assert r.b_total == 3
    assert r.b_top1_hits == 1
    assert r.b_top3_hits == 2


def test_gold_not_in_catalog_excluded_from_b_denominator():
    outcomes = [
        _m(expected_code="X.Y", catalog_has_code=False, matched_code=None, top3_codes=[]),
        _m(matched_code="1.1", top3_codes=["1.1"]),
    ]
    r = compute_metrics(outcomes)
    assert r.gold_not_in_catalog == 1
    assert r.b_total == 1  # узел с отсутствующим кодом не в знаменателе B


def test_article_renamed_flagged_when_catalog_name_differs():
    o = _m(catalog_name_norm="другое имя")  # снимок отличается → renamed
    r = compute_metrics([o])
    assert r.article_renamed == 1


def test_no_article_excluded_status_lands_in_other_bucket():
    outcomes = [
        _m(
            expected_kind=BenchmarkKind.NO_ARTICLE,
            expected_code=None,
            kept=False,
            status="excluded",
        ),
        _m(
            expected_kind=BenchmarkKind.NO_ARTICLE,
            expected_code=None,
            kept=True,
            status="no_match",
        ),
    ]
    r = compute_metrics(outcomes)
    assert r.no_article_total == 2
    assert r.no_article_other == 1
    assert (r.no_article_correct_no_match + r.no_article_wrong_confident
            + r.no_article_needs_review + r.no_article_other) == r.no_article_total
