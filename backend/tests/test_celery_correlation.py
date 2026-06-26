from __future__ import annotations

import app.core.logging_config as lc


class _Req:
    def __init__(self, request_id: str) -> None:
        self.request_id = request_id


class _Task:
    def __init__(self, request_id: str) -> None:
        self.request = _Req(request_id)


class _BareReq:
    pass


class _BareTask:
    def __init__(self) -> None:
        self.request = _BareReq()


def test_prerun_binds_then_postrun_resets() -> None:
    from app.infrastructure.tasks.celery_app import _on_task_postrun, _on_task_prerun

    _on_task_prerun(task_id="t-1", task=_Task("r-9"))
    assert lc.get_request_id() == "r-9"
    _on_task_postrun()
    assert lc.get_request_id() is None


def test_prerun_without_header_binds_none() -> None:
    from app.infrastructure.tasks.celery_app import _on_task_postrun, _on_task_prerun

    lc.bind_request_id("leftover")  # имитируем протёкший id от прошлой задачи
    _on_task_prerun(task_id="t-2", task=_BareTask())
    assert lc.get_request_id() is None  # getattr default None — не несём чужой id
    _on_task_postrun()


def test_enqueue_match_propagates_request_id(monkeypatch) -> None:
    import app.infrastructure.tasks.task_queue as tq

    captured: dict = {}
    monkeypatch.setattr(
        tq.match_estimate_task, "apply_async",
        lambda args, headers: captured.update(args=args, headers=headers),
    )
    lc.bind_request_id("req-42")
    try:
        tq.CeleryTaskQueue().enqueue_match(7)
    finally:
        lc.reset_correlation()
    assert captured["args"] == (7,)
    assert captured["headers"] == {"request_id": "req-42"}


def test_request_id_live_in_enqueue_through_threadpool(client, seed_estimate, auth_headers) -> None:
    """Сквозная цепочка: middleware bind → sync-роут (threadpool) → enqueue видит request_id.

    Покрывает нетривиальное: retrigger — sync-эндпоинт, FastAPI гонит его в threadpool;
    полагаемся на то, что anyio копирует contextvar в воркер-тред. Искусственный bind
    (тест выше) этого НЕ проверяет — здесь bind делает реальный middleware.
    """
    from app.api.deps import get_task_queue
    from app.core.logging_config import get_request_id
    from app.main import app

    eid, _ = seed_estimate

    captured: dict = {}

    class _CapturingQueue:
        def enqueue_match(self, estimate_id: int) -> None:
            captured["rid"] = get_request_id()  # читаем contextvar внутри роут-вызова

        def enqueue_articles_embed(self) -> None:
            pass

    app.dependency_overrides[get_task_queue] = lambda: _CapturingQueue()
    r = client.post(f"/api/estimates/{eid}/match", headers=auth_headers)
    assert r.status_code == 202
    assert captured["rid"] == r.headers["x-request-id"]  # тот же id, не '-' и не None
