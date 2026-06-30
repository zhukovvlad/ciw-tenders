"""Оркестрация матчинга одной сметы: embed → gate → match → статус. Зависит только от портов.

Чист от Celery: gate-неготовность сигналит DictionaryNotReadyError (ожидание/blocked решает
тонкая Celery-обёртка). Транзиент узла гасится инлайн в адаптерах (TransientError) и фиксируется
как error поузлово — без проброса в задачу (нет LLM-амплификации).
"""

from __future__ import annotations

import logging
import time
from collections import Counter

from app.domain.classification import (
    build_embedding_input,
    classify_lexical,
    is_excluded,
    leaf_flags,
    resolve_ancestor_indices,
)
from app.domain.entities import (
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
            "no_match=%d match_error=%d excluded=%d за %d мс",
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
        nodes = self._estimates.fetch_all_nodes(estimate_id)  # порядок по source_index
        if not nodes:
            return 0
        depths = [len(n.code.split(".")) for n in nodes]
        chains = resolve_ancestor_indices(depths)
        leafs = leaf_flags(depths)
        # Проход 1: лексика.
        cls_by_id: dict[int, WorkClass] = {}
        unsure_idx: list[int] = []
        for i, n in enumerate(nodes):
            cls = classify_lexical(n.name)
            cls_by_id[n.id] = cls
            if cls is WorkClass.UNSURE:
                unsure_idx.append(i)
        # Проход 1b: LLM по UNSURE — контекст предков из позиционной цепочки.
        if unsure_idx:
            items = [
                NodeToClassify(nodes[i].name, tuple(nodes[j].name for j in chains[i]))
                for i in unsure_idx
            ]
            verdicts = self._classifier.classify(items)
            for i, verdict in zip(unsure_idx, verdicts, strict=True):
                cls_by_id[nodes[i].id] = verdict
        # Проход 2: override + крошка → bulk.
        results: list[NodeClassification] = []
        for i, n in enumerate(nodes):
            ancestors = [(nodes[j].name, cls_by_id[nodes[j].id]) for j in chains[i]]
            own = cls_by_id[n.id]
            has_non_org_anc = any(cls is not WorkClass.ORG for _, cls in ancestors)
            excluded = is_excluded(own, is_leaf=leafs[i], has_non_org_ancestor=has_non_org_anc)
            crumb = build_embedding_input(n.name, ancestors, self_class=own)
            if not excluded and not crumb:
                logger.error(
                    "kept-узел с пустой крошкой: id=%s code=%s class=%s", n.id, n.code, own
                )
                raise AssertionError(f"kept node with empty crumb: {n.id} {n.code} {own}")
            results.append(
                NodeClassification(node_id=n.id, excluded=excluded, embedding_input=crumb)
            )
        self._estimates.save_node_classifications(results)
        return sum(1 for r in results if r.excluded)

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
