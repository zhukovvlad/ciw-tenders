from __future__ import annotations


def test_search_matches_code_and_name(client, auth_headers, article_repo):
    article_repo.add_article(id=1, code="1.4.1", name="Мокап фасада")
    article_repo.add_article(id=2, code="9.9", name="Демонтаж")
    resp = client.get("/api/articles/search?q=фасад", headers=auth_headers)
    assert resp.status_code == 200
    codes = [a["code"] for a in resp.json()]
    assert codes == ["1.4.1"]


def test_search_short_query_400(client, auth_headers):
    resp = client.get("/api/articles/search?q=ф", headers=auth_headers)
    assert resp.status_code == 400


def test_search_includes_unembedded(client, auth_headers, article_repo):
    # ручной подбор должен видеть статьи без эмбеддинга (embedding IS NULL)
    article_repo.add_article(id=3, code="2.2", name="Кровля")  # фейк: embedding=None
    resp = client.get("/api/articles/search?q=кров", headers=auth_headers)
    assert [a["code"] for a in resp.json()] == ["2.2"]
