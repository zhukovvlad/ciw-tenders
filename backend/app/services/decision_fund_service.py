"""Use-case золотого фонда: промоушен из ревью-решений, снятие источника, пересборка.

Предикат и анти-накрутка — здесь (бизнес-логика), репозитории дают примитивы.
"""

from __future__ import annotations

from app.domain.classification import CRUMB_DERIVATION_VERSION
from app.domain.decision_fund import FundEntry, cache_key_hash, normalize_cache_key
from app.domain.ports import DecisionFundRepository, EstimateRepository

_PROMOTABLE_REVIEW = {"confirmed", "overridden"}


class DecisionFundService:
    def __init__(self, estimates: EstimateRepository, fund: DecisionFundRepository) -> None:
        self._estimates = estimates
        self._fund = fund

    def promote(self, estimate_id: int) -> int:
        entries: list[FundEntry] = []
        for r in self._estimates.fetch_promotable_rows(estimate_id):
            if r.review_status not in _PROMOTABLE_REVIEW:
                continue
            # анти-накрутка: фонд-хит, который человек лишь ПОДТВЕРДИЛ, обратно не рекрутируем
            if r.status == "matched_fund" and r.review_status == "confirmed":
                continue
            if r.final_article_id is None:
                # перестраховка (confirmed/overridden гарантируют непустой, см. спеку §2.1)
                continue
            key = normalize_cache_key(r.embedding_input)
            entries.append(FundEntry(
                cache_key_hash=cache_key_hash(key), cache_key=key,
                crumb_version=CRUMB_DERIVATION_VERSION, article_id=r.final_article_id,
                source_estimate_id=estimate_id, source_row_id=r.row_id,
            ))
        self._fund.upsert(entries)
        # флаг ставим только если реально что-то запромоутили — иначе «пустая» эталонная смета
        # (0 confirmed-строк), которую rebuild гоняет вхолостую.
        # Эндпоинт вернёт count → UI подскажет.
        if entries:
            self._estimates.set_reference(estimate_id, True)
        return len(entries)

    def unreference(self, estimate_id: int) -> None:
        self._estimates.set_reference(estimate_id, False)

    def rebuild(self) -> None:
        self._fund.clear()
        for eid in self._estimates.fetch_reference_estimate_ids():
            self.promote(eid)
