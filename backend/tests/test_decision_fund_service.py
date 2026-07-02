"""Task 5: DecisionFundService — промоушен из ревью-решений, снятие источника, пересборка.

Предикат (confirmed/overridden) и анти-накрутка (matched_fund+confirmed не рекрутируется)
проверяются на фейках (см. tests/fakes.py: FakeEstimateRepository/FakeDecisionFundRepository).
"""

from __future__ import annotations

from app.domain.decision_fund import FundEntry, cache_key_hash, normalize_cache_key
from app.services.decision_fund_service import DecisionFundService
from tests.fakes import (
    FakeDecisionFundRepository,
    FakeEstimateRepository,
    Row,
    seed_estimate_with_rows,
)


def test_promote_takes_only_confirmed_overridden() -> None:
    repo, fund = FakeEstimateRepository(), FakeDecisionFundRepository()
    # строки: confirmed→в фонд, unreviewed→нет, confident-unreviewed→нет
    eid = seed_estimate_with_rows(
        repo,
        [
            Row("a", "needs_review", "confirmed", final_article_id=5),
            Row("b", "needs_review", "unreviewed", final_article_id=None),
            Row("c", "confident", "unreviewed", final_article_id=9),
        ],
    )
    DecisionFundService(repo, fund).promote(eid)
    keys = {k for (k, _v) in fund.entries}
    assert keys == {cache_key_hash(normalize_cache_key("a"))}  # только confirmed-строка
    assert repo.is_reference(eid) is True


def test_promote_anti_inflation_skips_confirmed_fund_hit() -> None:
    repo, fund = FakeEstimateRepository(), FakeDecisionFundRepository()
    eid = seed_estimate_with_rows(
        repo,
        [
            Row("a", "matched_fund", "confirmed", final_article_id=5),
            Row("b", "matched_fund", "overridden", final_article_id=7),
        ],
    )
    DecisionFundService(repo, fund).promote(eid)
    # matched_fund+confirmed НЕ промоутится (накрутка); matched_fund+overridden → промоутится
    assert (cache_key_hash(normalize_cache_key("a")), 1) not in fund.entries
    assert (cache_key_hash(normalize_cache_key("b")), 1) in fund.entries


def test_promote_dedupes_repeated_rows_in_one_batch() -> None:
    # Повторяющаяся работа = один ключ (ядро фичи): две строки с одинаковым embedding_input,
    # подтверждённые на одну статью, НЕ должны дать дубль conflict-ключа в одном upsert-батче
    # (Postgres: CardinalityViolation → 500 на PATCH /reference, rebuild умирает после clear()).
    repo, fund = FakeEstimateRepository(), FakeDecisionFundRepository()
    eid = seed_estimate_with_rows(
        repo,
        [
            Row("демонтаж перегородок", "needs_review", "confirmed", final_article_id=5),
            Row("демонтаж перегородок", "needs_review", "confirmed", final_article_id=5),
        ],
    )
    promoted = DecisionFundService(repo, fund).promote(eid)
    assert promoted == 1  # одна запись фонда, не две
    key = cache_key_hash(normalize_cache_key("демонтаж перегородок"))
    assert set(fund.entries) == {(key, 1)}
    assert repo.is_reference(eid) is True


def test_rebuild_clears_and_repromotes_reference_only() -> None:
    repo, fund = FakeEstimateRepository(), FakeDecisionFundRepository()
    e1 = seed_estimate_with_rows(repo, [Row("a", "needs_review", "confirmed", 5)])
    repo.set_reference(e1, True)
    seed_estimate_with_rows(repo, [Row("b", "needs_review", "confirmed", 9)])  # НЕ reference
    fund.upsert([FundEntry("stale", "stale", 1, 1, 0, 0)])
    DecisionFundService(repo, fund).rebuild()
    keys = {k for (k, _v) in fund.entries}
    assert keys == {cache_key_hash(normalize_cache_key("a"))}  # stale убран, e2 не вошёл
