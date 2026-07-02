"""Task 3 SP3: GET /estimates/{id} exposes candidates + review axis."""

from __future__ import annotations

from app.domain.entities import EstimateRowStatus, MatchCandidate, NodeMatch


def test_detail_exposes_candidates_and_review_axis(
    client, auth_headers, estimate_repo, seed_estimate
):
    eid, nid = seed_estimate  # смета с одним узлом
    estimate_repo.nodes[nid]["embedding"] = [0.1]
    estimate_repo.save_node_match(
        nid,
        NodeMatch(
            EstimateRowStatus.NEEDS_REVIEW, matched_id=7, matched_code="2.1",
            matched_name="Статья", score=0.7,
            candidates=[MatchCandidate(7, "2.1", "Статья", 0.7)],
        ),
    )
    resp = client.get(f"/api/estimates/{eid}", headers=auth_headers)
    assert resp.status_code == 200
    row = resp.json()["rows"][0]
    assert row["id"] == nid
    assert row["review_status"] == "unreviewed"
    assert row["candidates"][0]["code"] == "2.1"
    assert "source_index" not in row


def test_detail_exposes_is_reference(client, auth_headers, estimate_repo, seed_estimate):
    # UI гидратирует тумблер «в фонд» из серверного флага при повторном открытии сметы
    eid, _nid = seed_estimate
    resp = client.get(f"/api/estimates/{eid}", headers=auth_headers)
    assert resp.json()["is_reference"] is False
    estimate_repo.set_reference(eid, True)
    resp = client.get(f"/api/estimates/{eid}", headers=auth_headers)
    assert resp.json()["is_reference"] is True
