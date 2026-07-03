from __future__ import annotations

from app.domain.catalog_tree import ancestor_names_by_ids

# id -> (name, parent_id)
_NODES = {
    1: ("03 Фундаменты и основания", None),
    2: ("03.0 Устройство фундаментов", 1),
    3: ("03.04 Фундаменты под оборудование", 2),
    4: ("Сирота с битым parent_id", 99),
}


def test_chain_root_to_parent() -> None:
    assert ancestor_names_by_ids(_NODES, [3]) == {
        3: ["03 Фундаменты и основания", "03.0 Устройство фундаментов"]
    }


def test_root_has_empty_chain() -> None:
    assert ancestor_names_by_ids(_NODES, [1]) == {1: []}


def test_unknown_id_omitted() -> None:
    assert ancestor_names_by_ids(_NODES, [777]) == {}


def test_broken_parent_link_stops_walk() -> None:
    assert ancestor_names_by_ids(_NODES, [4]) == {4: []}


def test_cycle_guard() -> None:
    cyc = {1: ("A", 2), 2: ("B", 1)}
    out = ancestor_names_by_ids(cyc, [1])
    assert 1 in out and len(out[1]) <= 20  # не зависает, обход ограничен
