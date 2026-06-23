from __future__ import annotations


def test_retrigger_sweeps_stale_running(client, auth_headers, estimate_repo, seed_estimate):
    eid, _ = seed_estimate
    estimate_repo.statuses[eid] = "running"
    estimate_repo.stale_running.add(eid)  # фейк: помечаем «протухшим»
    resp = client.post(f"/api/estimates/{eid}/match", headers=auth_headers)
    assert resp.status_code == 202
    assert estimate_repo.statuses[eid] == "pending"  # сброшено
    assert "после сбоя" in resp.json()["detail"]


def test_retrigger_running_not_stale_no_reset(client, auth_headers, estimate_repo, seed_estimate):
    eid, _ = seed_estimate
    estimate_repo.statuses[eid] = "running"  # свежий heartbeat → не в stale_running
    resp = client.post(f"/api/estimates/{eid}/match", headers=auth_headers)
    assert resp.status_code == 202
    assert estimate_repo.statuses[eid] == "running"
    assert resp.json()["detail"] == "уже выполняется"


def test_retrigger_stale_but_lock_held_no_reset(client, auth_headers, estimate_repo, seed_estimate):
    eid, _ = seed_estimate
    estimate_repo.statuses[eid] = "running"
    estimate_repo.stale_running.add(eid)
    estimate_repo._locks.add(eid)  # живой воркер держит лок
    resp = client.post(f"/api/estimates/{eid}/match", headers=auth_headers)
    assert resp.status_code == 202
    assert estimate_repo.statuses[eid] == "running"  # не тронуто — лок занят
