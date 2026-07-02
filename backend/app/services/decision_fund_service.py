"""Use-case золотого фонда: промоушен из ревью-решений, снятие источника, пересборка.

Предикат и анти-накрутка — здесь (бизнес-логика), репозитории дают примитивы.
"""

from __future__ import annotations

import logging

from app.domain.classification import CRUMB_DERIVATION_VERSION
from app.domain.decision_fund import FundEntry, cache_key_hash, normalize_cache_key
from app.domain.ports import DecisionFundRepository, EstimateRepository

logger = logging.getLogger(__name__)

_PROMOTABLE_REVIEW = {"confirmed", "overridden"}


class DecisionFundService:
    def __init__(self, estimates: EstimateRepository, fund: DecisionFundRepository) -> None:
        self._estimates = estimates
        self._fund = fund

    def promote(self, estimate_id: int) -> int:
        # дедуп по conflict-ключу: повторяющаяся работа в одной смете даёт один и тот же ключ,
        # а дубль в одном INSERT..ON CONFLICT DO UPDATE — CardinalityViolation в Postgres
        by_key: dict[tuple[str, int, int], FundEntry] = {}
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
            key_hash = cache_key_hash(key)
            by_key.setdefault(
                (key_hash, CRUMB_DERIVATION_VERSION, r.final_article_id),
                FundEntry(
                    cache_key_hash=key_hash, cache_key=key,
                    crumb_version=CRUMB_DERIVATION_VERSION, article_id=r.final_article_id,
                    source_estimate_id=estimate_id, source_row_id=r.row_id,
                ),
            )
        entries = list(by_key.values())
        self._fund.upsert(entries)
        # флаг ставим только если реально что-то запромоутили — иначе «пустая» эталонная смета
        # (0 confirmed-строк), которую rebuild гоняет вхолостую.
        # Эндпоинт вернёт count → UI подскажет.
        if entries:
            self._estimates.set_reference(estimate_id, True)
        logger.info(
            "Промоушен фонда: estimate_id=%s, записей=%d",
            estimate_id,
            len(entries),
            extra={"estimate_id": estimate_id, "promoted": len(entries)},
        )
        return len(entries)

    def unreference(self, estimate_id: int) -> None:
        """Снять смету из набора эталонов (is_reference=False).

        НАМЕРЕННО снимает только флаг: строки, уже записанные этой сметой в фонд, остаются
        активными до ближайшего rebuild(). Точечно удалить «вклад одной сметы» нельзя — фонд
        хранит лишь последнего вкладчика (source_*), а один ключ разделяют несколько эталонных
        смет (votes), поэтому delete по source_estimate_id снёс бы чужие подтверждения.
        Корректная инвалидация = снять флаг + rebuild() (детерминированно пересобирает из
        оставшихся эталонов). См. спеку §9.
        """
        self._estimates.set_reference(estimate_id, False)

    def rebuild(self) -> None:
        self._fund.clear()
        reference_ids = self._estimates.fetch_reference_estimate_ids()
        for eid in reference_ids:
            self.promote(eid)
        logger.info(
            "Пересборка фонда завершена: эталонных смет=%d",
            len(reference_ids),
            extra={"reference_estimates": len(reference_ids)},
        )
