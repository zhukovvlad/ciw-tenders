"""Юниты позиционного резолва иерархии (стек по глубине-кода). Чистый домен, без БД/AI.

Глубина здесь = число сегментов кода (`6.4.1` → 3); стек смотрит ТОЛЬКО вверх,
поэтому forward-ref невозможен, а индексы предков строго возрастают и < i.
"""

from __future__ import annotations

import random

from app.domain.classification import (
    canonical_codes,
    detect_structural_anomalies,
    leaf_flags,
    resolve_ancestor_indices,
)
from app.domain.entities import StructuralAnomaly

# --- resolve_ancestor_indices ------------------------------------------------


def test_resolve_collision_gives_different_ancestors() -> None:
    # A(1) B(2) C(3) | D(2) E(3): C и E — оба «глубины 3», но РАЗНЫЕ предки d2.
    # Это коллизия дублей кодов: одинаковый код 6.4.1 в двух этапах → разные родители.
    depths = [1, 2, 3, 2, 3]
    chains = resolve_ancestor_indices(depths)
    assert chains[2] == [0, 1]  # C → [A, B]
    assert chains[4] == [0, 3]  # E → [A, D], НЕ [A, B] (не первое вхождение d2)


def test_resolve_skips_missing_level_takes_nearest_open() -> None:
    # «газон»: Озеленение(2) Покрытие(3) газон(5) — уровень 4 пропущен.
    # Предок газона — ближайший открытый (Покрытие, d3), а не None и не стейл.
    depths = [2, 3, 5]
    chains = resolve_ancestor_indices(depths)
    assert chains[2] == [0, 1]  # газон → [Озеленение, Покрытие], d4 выпал


def test_resolve_root_has_no_ancestors() -> None:
    assert resolve_ancestor_indices([1, 1, 1]) == [[], [], []]


def test_resolve_sibling_closes_previous() -> None:
    # B(2) и D(2) — сёстры под A(1); D не должен наследовать предков B.
    depths = [1, 2, 2]
    chains = resolve_ancestor_indices(depths)
    assert chains == [[], [0], [0]]


def test_resolve_property_monotonic_and_below_i() -> None:
    rnd = random.Random(20260630)
    for _ in range(500):
        n = rnd.randint(1, 30)
        depths = [rnd.randint(1, 6) for _ in range(n)]
        for i, chain in enumerate(resolve_ancestor_indices(depths)):
            assert all(j < i for j in chain), (depths, i, chain)
            assert chain == sorted(chain), (depths, i, chain)
            assert len(set(chain)) == len(chain), (depths, i, chain)
            # глубины предков строго возрастают и все < depths[i]
            anc_depths = [depths[j] for j in chain]
            assert anc_depths == sorted(anc_depths)
            assert all(d < depths[i] for d in anc_depths)


# --- leaf_flags --------------------------------------------------------------


def test_leaf_flags_basic() -> None:
    assert leaf_flags([1, 2, 2]) == [False, True, True]
    assert leaf_flags([1, 2, 3]) == [False, False, True]
    assert leaf_flags([1, 2, 1]) == [False, True, True]


def test_leaf_flags_single_and_empty() -> None:
    assert leaf_flags([1]) == [True]
    assert leaf_flags([]) == []


def test_leaf_flags_collision_branch() -> None:
    # A(1) B(2) C(3) D(2) E(3): B не лист (есть C), D не лист (есть E), C/E листья.
    assert leaf_flags([1, 2, 3, 2, 3]) == [False, False, True, False, True]


# --- canonical_codes ---------------------------------------------------------


def test_canonical_simple_tree() -> None:
    assert canonical_codes([1, 2, 3]) == ["1", "1.1", "1.1.1"]
    assert canonical_codes([1, 2, 2, 1]) == ["1", "1.1", "1.2", "2"]


def test_canonical_compresses_missing_levels() -> None:
    # газон [2,3,5]: канон отражает РЕАЛЬНОЕ дерево (len предков+1), не номинальную глубину 5.
    assert canonical_codes([2, 3, 5]) == ["1", "1.1", "1.1.1"]


def test_canonical_collision() -> None:
    assert canonical_codes([1, 2, 3, 2, 3]) == ["1", "1.1", "1.1.1", "1.2", "1.2.1"]


# --- detect_structural_anomalies ---------------------------------------------
# Вход: список (source_index, code, name, outline_level) в порядке документа (coded-узлы).
# Выход: (list[StructuralAnomaly], outline_overrides: int). outline_code_mismatch — АГРЕГАТ.


def _kinds(anoms: list[StructuralAnomaly]) -> set[str]:
    return {a.kind for a in anoms}


def test_detect_duplicate_code() -> None:
    rows = [(0, "1", "A", 0), (1, "1.1", "B", 1), (2, "1.1", "C", 1)]
    anoms, _ = detect_structural_anomalies(rows)
    dups = [a for a in anoms if a.kind == "duplicate_code"]
    assert {a.source_index for a in dups} == {1, 2}  # оба вхождения
    assert all(a.detail == "код встречается 2 раза" for a in dups)  # склонение «раза», не «раз»


def test_detect_parent_below() -> None:
    # 1.1 встречается НИЖЕ своего ребёнка 1.1.1
    rows = [(0, "1", "A", 0), (1, "1.1.1", "child", 2), (2, "1.1", "parent", 1)]
    anoms, _ = detect_structural_anomalies(rows)
    pb = [a for a in anoms if a.kind == "parent_below"]
    assert [a.source_index for a in pb] == [1]


def test_detect_parent_missing() -> None:
    rows = [(0, "11", "A", 0), (1, "11.3.1.1.1", "газон", 4)]
    anoms, _ = detect_structural_anomalies(rows)
    assert "parent_missing" in _kinds(anoms)
    pm = next(a for a in anoms if a.kind == "parent_missing")
    assert pm.source_index == 1


def test_detect_depth_jump() -> None:
    rows = [(0, "1", "A", 0), (1, "1.1.1.1", "deep", 3)]
    anoms, _ = detect_structural_anomalies(rows)
    assert "depth_jump" in _kinds(anoms)


def test_outline_mismatch_is_aggregate_not_rowwise() -> None:
    # outline+1 != сегменты на двух строках → счётчик 2, и НИ одной построчной аномалии этого вида
    rows = [(0, "6", "Фасады", 0), (1, "6.2", "Светопроз", 2), (2, "6.2.1", "Профиль", 3)]
    anoms, overrides = detect_structural_anomalies(rows)
    assert overrides == 2  # 6.2 (1+1≠2? outline2→3 vs seg2) и 6.2.1 (outline3→4 vs seg3)
    assert all(a.kind != "outline_code_mismatch" for a in anoms)


def test_clean_input_no_anomalies() -> None:
    rows = [(0, "1", "A", 0), (1, "1.1", "B", 1), (2, "1.1.1", "C", 2)]
    anoms, overrides = detect_structural_anomalies(rows)
    assert anoms == []
    assert overrides == 0
