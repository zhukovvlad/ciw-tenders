"""Оркестрация матчинга одной сметы: embed → gate → match → статус. Зависит только от портов.

Чист от Celery: gate-неготовность сигналит DictionaryNotReadyError (ожидание/blocked решает
тонкая Celery-обёртка). Транзиент узла гасится инлайн в адаптерах (TransientError) и фиксируется
как error поузлово — без проброса в задачу (нет LLM-амплификации).
"""

from __future__ import annotations

import logging
import time
from collections import Counter

from app.domain.classification import build_embedding_input, classify_lexical
from app.domain.entities import (
    ClassifiableNode,
    EstimateRowStatus,
    EstimateStatus,
    NodeClassification,
    NodeMatch,
    NodeToClassify,
    WorkClass,
)
from app.domain.errors import DictionaryNotReadyError, TransientError
from app.domain.ports import ArticleRepository, Embedder, EstimateRepository, WorkTypeClassifier
from app.services.matching_service import MatchingService

_EMBED_CHUNK = 100
_HEARTBEAT_EVERY = 50
_TERMINAL = (EstimateStatus.READY, EstimateStatus.PARTIAL_ERROR)

logger = logging.getLogger(__name__)


class EstimateMatchingService:
    def __init__(
        self,
        matcher: MatchingService,
        embedder: Embedder,
        estimates: EstimateRepository,
        articles: ArticleRepository,
        classifier: WorkTypeClassifier,
    ) -> None:
        self._matcher = matcher
        self._embedder = embedder
        self._estimates = estimates
        self._articles = articles
        self._classifier = classifier

    def match_estimate(self, estimate_id: int) -> None:
        if not self._estimates.try_matching_lock(estimate_id):
            return  # конкурент владеет → no-op
        start = time.monotonic()
        excluded = 0
        counts: Counter[EstimateRowStatus] = Counter()
        try:
            self._estimates.set_status(estimate_id, EstimateStatus.RUNNING)  # COMMIT до embed
            excluded = self._classify_nodes(estimate_id)
            logger.debug(
                "Матчинг %s: классификация завершена (ORG-исключено: %d)", estimate_id, excluded
            )
            self._embed_nodes(estimate_id)
            logger.debug("Матчинг %s: эмбеддинг завершён", estimate_id)
            total, pending = self._articles.matching_readiness()
            if total == 0 or pending > 0:
                raise DictionaryNotReadyError(total=total, pending=pending)
            counts = self._match_nodes(estimate_id)
            logger.debug("Матчинг %s: сопоставление завершено", estimate_id)
            errors = self._estimates.count_node_errors(estimate_id)
            unfinished = self._estimates.count_unfinished_nodes(estimate_id)
            if errors or unfinished:
                self._estimates.set_status(
                    estimate_id,
                    EstimateStatus.PARTIAL_ERROR,
                    detail=f"errors={errors} unfinished={unfinished}",
                )
            else:
                self._estimates.set_status(estimate_id, EstimateStatus.READY)
            self._log_summary(estimate_id, counts, excluded, start)
        except DictionaryNotReadyError:
            raise  # gate: обёртка ретраит/блокирует — summary НЕ пишем (не терминал)
        except Exception as exc:  # noqa: BLE001 — непредвиденный сбой не оставляем в running
            self._estimates.set_status(
                estimate_id, EstimateStatus.PARTIAL_ERROR, detail=f"unexpected: {exc}"
            )
            self._log_summary(estimate_id, counts, excluded, start)
            raise
        finally:
            self._estimates.release_matching_lock(estimate_id)

    def _log_summary(
        self,
        estimate_id: int,
        counts: Counter[EstimateRowStatus],
        excluded: int,
        start: float,
    ) -> None:
        duration_ms = round((time.monotonic() - start) * 1000)
        status = self._estimates.get_status(estimate_id)
        logger.info(
            "Матчинг сметы %s завершён: статус=%s confident=%d needs_review=%d "
            "no_match=%d error=%d excluded=%d за %d мс",
            estimate_id,
            getattr(status, "value", status),
            counts[EstimateRowStatus.CONFIDENT],
            counts[EstimateRowStatus.NEEDS_REVIEW],
            counts[EstimateRowStatus.NO_MATCH],
            counts[EstimateRowStatus.ERROR],
            excluded,
            duration_ms,
            extra={
                "estimate_id": estimate_id,
                "confident": counts[EstimateRowStatus.CONFIDENT],
                "needs_review": counts[EstimateRowStatus.NEEDS_REVIEW],
                "no_match": counts[EstimateRowStatus.NO_MATCH],
                "match_error": counts[EstimateRowStatus.ERROR],
                "excluded": excluded,
                "latency_ms": duration_ms,
            },
        )

    def _classify_nodes(self, estimate_id: int) -> int:
        nodes = self._estimates.fetch_all_nodes(estimate_id)
        if not nodes:
            return 0
        # Представители по коду (первое вхождение) — только для крошки предков.
        name_by_code: dict[str, str] = {}
        repr_id_by_code: dict[str, int] = {}
        for n in nodes:
            name_by_code.setdefault(n.code, n.name)
            repr_id_by_code.setdefault(n.code, n.id)
        # Проход 1: лексика. Собственный класс — по id. UNSURE копим для LLM.
        cls_by_id: dict[int, WorkClass] = {}
        unsure: list[ClassifiableNode] = []
        for n in nodes:
            cls = classify_lexical(n.name)
            cls_by_id[n.id] = cls
            if cls is WorkClass.UNSURE:
                unsure.append(n)
        # Проход 1b: LLM по неоднозначным (UNSURE-вердикт остаётся = keep).
        if unsure:
            items = [
                NodeToClassify(n.name, self._ancestor_names(n.code, name_by_code))
                for n in unsure
            ]
            for n, verdict in zip(unsure, self._classifier.classify(items), strict=True):
                cls_by_id[n.id] = verdict
        # Проход 2: собрать результаты + пересборка крошки (ORG-предки выброшены) → bulk-запись.
        results: list[NodeClassification] = []
        for n in nodes:
            ancestors = [
                (name_by_code[a], cls_by_id[repr_id_by_code[a]])
                for a in self._ancestor_codes(n.code)
                if a in name_by_code
            ]
            crumb = build_embedding_input(n.name, ancestors)
            # ORG из ЛЮБОГО источника (лексика row-2 ИЛИ вердикт LLM) → excluded.
            # Класс берём по n.id — дубли кода НЕ схлопываются.
            results.append(
                NodeClassification(
                    node_id=n.id,
                    excluded=cls_by_id[n.id] is WorkClass.ORG,
                    embedding_input=crumb,
                )
            )
        self._estimates.save_node_classifications(results)  # один commit, охрана статуса
        return sum(1 for r in results if r.excluded)

    @staticmethod
    def _ancestor_codes(code: str) -> list[str]:
        segs = code.split(".")
        return [".".join(segs[:i]) for i in range(1, len(segs))]  # root..parent, без узла

    def _ancestor_names(self, code: str, name_by_code: dict[str, str]) -> tuple[str, ...]:
        return tuple(name_by_code[a] for a in self._ancestor_codes(code) if a in name_by_code)

    def _embed_nodes(self, estimate_id: int) -> None:
        last_id = 0
        while chunk := self._estimates.fetch_unembedded_nodes(
            estimate_id, after_id=last_id, limit=_EMBED_CHUNK
        ):
            try:
                vectors = self._embedder.embed_batch([n.embedding_input for n in chunk])
                for node, vector in zip(chunk, vectors, strict=True):
                    self._estimates.save_node_embedding(node.id, node.embedding_input, vector)
            except TransientError:
                pass  # узлы остаются pending → unfinished → partial_error (ре-триггер доберёт)
            self._estimates.touch(estimate_id)  # heartbeat
            last_id = chunk[-1].id

    def _match_nodes(self, estimate_id: int) -> Counter[EstimateRowStatus]:
        counts: Counter[EstimateRowStatus] = Counter()
        for i, node in enumerate(self._estimates.fetch_matchable_nodes(estimate_id), start=1):
            try:
                result = self._matcher.match_one(node.embedding, node.embedding_input)
            except TransientError as exc:  # адаптер исчерпал инлайн-бюджет
                result = NodeMatch(EstimateRowStatus.ERROR, match_error=str(exc))
            counts[result.status] += 1
            self._estimates.save_node_match(node.id, result)
            if i % _HEARTBEAT_EVERY == 0:
                self._estimates.touch(estimate_id)
        return counts

    def mark_blocked(self, estimate_id: int, detail: str) -> None:
        """Вызывается обёрткой при исчерпании gate-retry. Под локом, не затирает реальный
        результат."""
        if not self._estimates.try_matching_lock(estimate_id):
            return  # активный матчер → no-op
        try:
            if self._estimates.get_status(estimate_id) in _TERMINAL:
                return  # B успел сматчить на границе ретраев → не клоббим
            self._estimates.set_status(estimate_id, EstimateStatus.BLOCKED, detail=detail)
        finally:
            self._estimates.release_matching_lock(estimate_id)
