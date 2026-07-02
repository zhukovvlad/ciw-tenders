from __future__ import annotations

from app.domain.entities import EstimateRowStatus, MatchCandidate, NodeMatch


def _match(repo, nid, status, *, mid=None, code=None, name=None, score=None, cands=()):
    repo.nodes[nid]["embedding"] = [0.1]
    repo.save_node_match(
        nid,
        NodeMatch(status, matched_id=mid, matched_code=code, matched_name=name,
                  score=score, candidates=list(cands)),
    )


def test_confirm_needs_review_freezes_matched(client, auth_headers, estimate_repo, seed_estimate):
    eid, nid = seed_estimate
    _match(estimate_repo, nid, EstimateRowStatus.NEEDS_REVIEW, mid=7, code="2.1",
           name="Статья", score=0.7, cands=[MatchCandidate(7, "2.1", "Статья", 0.7)])
    resp = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers, json={"action": "confirm"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["review_status"] == "confirmed"
    assert body["final_code"] == "2.1"
    assert body["final_article_id"] == 7


def test_confirm_no_match_is_422(client, auth_headers, estimate_repo, seed_estimate):
    eid, nid = seed_estimate
    _match(estimate_repo, nid, EstimateRowStatus.NO_MATCH)
    resp = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers, json={"action": "confirm"},
    )
    assert resp.status_code == 422


def test_pick_candidate_overridden(client, auth_headers, estimate_repo, seed_estimate):
    eid, nid = seed_estimate
    _match(estimate_repo, nid, EstimateRowStatus.NEEDS_REVIEW, mid=7, code="2.1",
           name="Статья", score=0.7,
           cands=[MatchCandidate(7, "2.1", "Статья", 0.7), MatchCandidate(9, "3.2", "Иная", 0.5)])
    resp = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers, json={"action": "pick", "article_id": 9},
    )
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "overridden"
    assert resp.json()["final_code"] == "3.2"  # заморожено из снимка кандидата


def test_pick_manual_from_catalog(client, auth_headers, estimate_repo, article_repo, seed_estimate):
    eid, nid = seed_estimate
    _match(estimate_repo, nid, EstimateRowStatus.NO_MATCH)
    article_repo.add_article(id=42, code="9.9", name="Ручная")  # хелпер фейка
    resp = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers, json={"action": "pick", "article_id": 42},
    )
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "overridden"
    assert resp.json()["final_code"] == "9.9"


def test_reject_clears_final(client, auth_headers, estimate_repo, seed_estimate):
    eid, nid = seed_estimate
    _match(estimate_repo, nid, EstimateRowStatus.NO_MATCH)
    resp = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers, json={"action": "reject"},
    )
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "rejected"
    assert resp.json()["final_code"] is None


def test_review_pending_row_409(client, auth_headers, estimate_repo, seed_estimate):
    eid, nid = seed_estimate  # status=pending по умолчанию
    resp = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers, json={"action": "confirm"},
    )
    assert resp.status_code == 409


def test_review_foreign_estimate_404(client, other_auth_headers, estimate_repo, seed_estimate):
    eid, nid = seed_estimate
    _match(estimate_repo, nid, EstimateRowStatus.NEEDS_REVIEW, mid=7, code="2.1",
           name="Статья", score=0.7, cands=[MatchCandidate(7, "2.1", "Статья", 0.7)])
    resp = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=other_auth_headers, json={"action": "confirm"},
    )
    assert resp.status_code == 404


def test_pick_and_reject_keep_ai_snapshot(
    client, auth_headers, estimate_repo, seed_estimate
):
    """Два инварианта из спеки editable-confident-rows §2:
    1) ревью пишет только ось review_status/final_* — AI-снимок matched_*/candidates
       иммутабелен (на этом держится откат «вернуть рекомендацию» на фронте);
    2) pick исходной рекомендации нормализуется в confirmed, не overridden
       (откат confident-строки через клик по топ-3 не застревает в «Ручной выбор»).
    """
    eid, nid = seed_estimate
    _match(
        estimate_repo,
        nid,
        EstimateRowStatus.NEEDS_REVIEW,
        mid=7,
        code="2.1",
        name="Статья",
        score=0.7,
        cands=[
            MatchCandidate(7, "2.1", "Статья", 0.7),
            MatchCandidate(9, "3.2", "Иная", 0.5),
        ],
    )

    picked = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers,
        json={"action": "pick", "article_id": 9},
    )
    assert picked.status_code == 200
    assert picked.json()["review_status"] == "overridden"
    assert picked.json()["matched_article_id"] == 7  # снимок не мутировал
    assert picked.json()["matched_code"] == "2.1"

    # снимок иммутабелен целиком: candidates тоже не тронуты
    assert [c["id"] for c in picked.json()["candidates"]] == [7, 9]

    rejected = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers,
        json={"action": "reject"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["matched_article_id"] == 7
    assert rejected.json()["matched_code"] == "2.1"

    # нормализация (_pick): выбор исходной рекомендации = confirmed, не overridden —
    # поэтому «откат» у confident-строки (клик по исходному кандидату в топ-3)
    # не застревает в «Ручной выбор» (спека §2)
    restored = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers,
        json={"action": "pick", "article_id": 7},
    )
    assert restored.status_code == 200
    assert restored.json()["review_status"] == "confirmed"
    assert restored.json()["final_code"] == "2.1"
