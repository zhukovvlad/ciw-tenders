from __future__ import annotations

import io

import pandas as pd
import pytest

from app.domain.entities import EstimateNode, NewEstimate
from app.services.estimate_parser import EstimateParser
from app.services.estimate_service import EstimateService
from tests.fakes import FakeEstimateRepository, FakeObjectStorage, FakeTaskQueue


def _node(code: str) -> EstimateNode:
    return EstimateNode(code, f"имя {code}", None, "СМР", f"ei {code}", 0, len(code.split(".")))


def _xlsx() -> bytes:
    df = pd.DataFrame(
        [("1", "Раздел", "СМР"), ("1.1", "Под", None), (None, "Позиция", None)],
        columns=["№ раздела", "Наименование раздела / позиции", "Вид раздела"],
    )
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def _service(storage: FakeObjectStorage) -> tuple[EstimateService, FakeEstimateRepository]:
    repo = FakeEstimateRepository()
    return EstimateService(EstimateParser(), repo, storage, task_queue=FakeTaskQueue()), repo


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


def test_ingest_puts_file_then_saves_nodes_pending() -> None:
    storage = FakeObjectStorage()
    service, repo = _service(storage)
    result = service.ingest(_xlsx(), "смета.xlsx", owner_id=7)
    assert result.estimate.status == "pending"
    assert [r.code for r in result.estimate.rows] == ["1", "1.1"]
    assert all(r.status == "pending" and not r.has_embedding for r in result.estimate.rows)
    assert result.positions_count == 1
    assert len(storage.put_calls) == 1            # файл загружен
    assert repo.create_calls == 1


def test_ingest_storage_failure_does_not_touch_db() -> None:
    from app.domain.errors import StorageError

    storage = FakeObjectStorage(fail=True)
    service, repo = _service(storage)
    with pytest.raises(StorageError):
        service.ingest(_xlsx(), "смета.xlsx", owner_id=7)
    assert repo.create_calls == 0                 # порядок put→INSERT соблюдён


def test_delete_removes_db_and_object() -> None:
    storage = FakeObjectStorage()
    service, repo = _service(storage)
    est = service.ingest(_xlsx(), "смета.xlsx", owner_id=7).estimate
    assert service.delete(est.id, requester_id=7, is_admin=False) is True
    assert storage.delete_calls  # объект удалён best-effort
    assert service.get(est.id, requester_id=7, is_admin=False) is None


def test_ingest_enqueues_match_after_create() -> None:
    from tests.fakes import FakeTaskQueue

    storage = FakeObjectStorage()
    repo = FakeEstimateRepository()
    queue = FakeTaskQueue()
    service = EstimateService(EstimateParser(), repo, storage, task_queue=queue)
    est = service.ingest(_xlsx(), "смета.xlsx", owner_id=7).estimate
    assert queue.match_calls == [est.id]          # энкью был
    assert repo.create_calls == 1                  # и строки уже созданы (после коммита)


def test_ingest_storage_failure_does_not_enqueue() -> None:
    from app.domain.errors import StorageError
    from tests.fakes import FakeTaskQueue

    queue = FakeTaskQueue()
    service = EstimateService(EstimateParser(), FakeEstimateRepository(),
                              FakeObjectStorage(fail=True), task_queue=queue)
    import pytest
    with pytest.raises(StorageError):
        service.ingest(_xlsx(), "смета.xlsx", owner_id=7)
    assert queue.match_calls == []                 # сбой put → ни БД, ни enqueue


def test_ingest_survives_broker_failure() -> None:
    from tests.fakes import FakeTaskQueue

    class _BoomQueue(FakeTaskQueue):
        def enqueue_match(self, estimate_id: int) -> None:
            raise RuntimeError("redis down")

    service = EstimateService(EstimateParser(), FakeEstimateRepository(),
                              FakeObjectStorage(), task_queue=_BoomQueue())
    result = service.ingest(_xlsx(), "смета.xlsx", owner_id=7)  # НЕ падает
    assert result.estimate.status == "pending"     # смета создана, ждёт ручного ре-триггера
