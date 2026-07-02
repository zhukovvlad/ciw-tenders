from __future__ import annotations

from app.domain.decision_fund import (
    cache_key_hash,
    normalize_cache_key,
    resolve_fund_decision,
)


def test_normalize_collapses_case_and_whitespace() -> None:
    a = normalize_cache_key("Подготовительные  работы. \tМОКАП ")
    b = normalize_cache_key("подготовительные работы. мокап")
    assert a == b == "подготовительные работы. мокап"


def test_hash_is_stable_and_hex64() -> None:
    h = cache_key_hash("подготовительные работы. мокап")
    assert h == cache_key_hash("подготовительные работы. мокап")
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


def test_resolve_single_live_answer() -> None:
    assert resolve_fund_decision([7]) == 7
    assert resolve_fund_decision([7, 7, 7]) == 7  # повторы одной статьи → она


def test_resolve_conflict_and_empty_give_none() -> None:
    assert resolve_fund_decision([7, 9]) is None   # конфликт
    assert resolve_fund_decision([]) is None        # промах/только мёртвые
