"""Тесты семантики фонда против FakeDecisionFundRepository (зеркало SQL-контракта).

Проверяем то, на что опирается сервис (Tasks 5/6): честность фейка по живости
(JOIN-фильтр в реальном репо) и фильтрацию по версии крошки. votes/source на
фейке не тестируем (инертны в v1; реальный on_conflict — track 3, интеграция).
"""

from __future__ import annotations

from app.domain.decision_fund import FundHit
from tests.fakes import FakeDecisionFundRepository


def test_lookup_returns_only_live_articles() -> None:
    fund = FakeDecisionFundRepository()
    fund.seed_hit("h1", 1, FundHit(article_id=5, code="1.4", name="Мокап"))
    fund.seed_hit("h1", 1, FundHit(article_id=999999, code="9.9", name="Мёртвая"))
    fund.dead_ids.add(999999)

    hits = fund.lookup(["h1"], crumb_version=1)

    assert [h.article_id for h in hits["h1"]] == [5]
    assert hits["h1"][0].name == "Мокап"


def test_lookup_filters_by_version() -> None:
    fund = FakeDecisionFundRepository()
    fund.seed_hit("h2", 1, FundHit(article_id=5, code="1.4", name="Мокап"))

    assert fund.lookup(["h2"], crumb_version=2) == {}


def test_lookup_drops_key_when_all_hits_dead() -> None:
    fund = FakeDecisionFundRepository()
    fund.seed_hit("h3", 1, FundHit(article_id=5, code="1.4", name="Мокап"))
    fund.dead_ids.add(5)

    assert fund.lookup(["h3"], crumb_version=1) == {}
