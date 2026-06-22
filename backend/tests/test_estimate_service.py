from __future__ import annotations

from app.domain.entities import EstimateNode, NewEstimate
from tests.fakes import FakeEstimateRepository, FakeObjectStorage


def _node(code: str) -> EstimateNode:
    return EstimateNode(code, f"имя {code}", None, "СМР", f"ei {code}", 0, len(code.split(".")))


def test_repo_ownership_isolation() -> None:
    repo = FakeEstimateRepository()
    repo.create(NewEstimate(1, "a.xlsx", "k1"), [_node("1")])
    repo.create(NewEstimate(2, "b.xlsx", "k2"), [_node("1")])
    assert [s.id for s in repo.list_for_owner(1, is_admin=False)] == [1]
    assert {s.id for s in repo.list_for_owner(9, is_admin=True)} == {1, 2}
    assert repo.get(2, requester_id=1, is_admin=False) is None
    assert repo.delete(1, requester_id=2, is_admin=False) is None  # чужая
    assert repo.delete(1, requester_id=1, is_admin=False) == "k1"  # ключ объекта


def test_fake_storage_records_calls() -> None:
    s = FakeObjectStorage()
    s.put("k", b"data", "x")
    assert s.put_calls == ["k"] and s.get("k") == b"data"
    s.delete("k")
    assert s.delete_calls == ["k"]
