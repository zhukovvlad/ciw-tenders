"""Оркестрация tree-движка: чанки → LLM → валидация → CAS (спека 2026-08-27 §4).

Сервис не импортирует `infrastructure` (направление зависимостей api → services →
domain ← infrastructure). Бюджет чанка оценивается по ДАННЫМ, консервативно —
никогда рендером текста промпта (это дело адаптера).
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence

from app.domain.entities import (
    AncestorContext,
    EstimateRowStatus,
    NodeMatch,
    SectionMatchRequest,
    TreeNode,
)
from app.domain.errors import DomainError, TransientError
from app.domain.ports import ArticleRepository, EstimateRepository, TreeMatcher
from app.domain.tree_matching import (
    Chunk,
    build_hints,
    effective_ancestor_context,
    estimate_tokens,
    hint_for,
    resolve_parents,
    split_sections,
    to_node_match,
    validate_one,
)

logger = logging.getLogger(__name__)

EXPECTED = ("pending", "error", "no_match")
ERR_TRANSIENT = "tree_transient"
ERR_ANCESTOR_FAILED = "tree_ancestor_failed"
ERR_TRUNCATED = "tree_output_truncated"
ERR_ROW_TOO_LARGE = "tree_row_too_large"
_CATALOG_SHARE = 0.25
_CONTEXT_SHARE = 0.80
_SYSTEM_PROMPT_RESERVE = 1_500  # системный промпт + заголовки блоков (факт спайка ~900)
_ANCESTORS_RESERVE = 600  # путь предков чанка (глубина ≤ 6 × ~100 токенов)
_OUTPUT_MARGIN = 512  # = запас адаптера в max_tokens
_ROW_FORMAT_TOKENS = 8  # «[цель] id | код | » + перенос


class CatalogEmptyError(DomainError):
    code = "catalog_empty"


class CatalogTooLargeError(DomainError):
    code = "catalog_too_large"


class TreeMatchingRunner:
    """Обходит дерево сметы чанками, вызывает `TreeMatcher` и пишет результат под CAS."""

    def __init__(
        self,
        *,
        matcher: TreeMatcher,
        estimates: EstimateRepository,
        articles: ArticleRepository,
        chunk_rows: int,
        min_chunk_rows: int,
        context_window: int,
        output_reserve_per_row: int,
        fund_enabled: bool = False,
    ) -> None:
        if fund_enabled:
            raise NotImplementedError("фонд v3 для tree-движка — PR 3 спеки")
        self._matcher = matcher
        self._estimates = estimates
        self._articles = articles
        self._chunk_rows = chunk_rows
        self._min_rows = min_chunk_rows
        self._window = context_window
        self._reserve = output_reserve_per_row

    def run(self, estimate_id: int) -> Counter[EstimateRowStatus]:
        catalog_list = self._articles.list_catalog()
        if not catalog_list:
            raise CatalogEmptyError("справочник пуст")
        catalog_tokens = sum(
            estimate_tokens("  " * a.code.count(".") + f"({a.code}) {a.name}") for a in catalog_list
        )
        if catalog_tokens > _CATALOG_SHARE * self._window:
            raise CatalogTooLargeError(
                f"справочник ~{catalog_tokens} токенов > 25% окна {self._window}"
            )
        catalog = {a.code: a for a in catalog_list}
        tree = list(self._estimates.fetch_tree(estimate_id))
        parents = resolve_parents(tree)
        counts: Counter[EstimateRowStatus] = Counter()
        failed_roots: set[int] = set()
        # Бюджет чанка (спека §5.2, консервативно): system + catalog + ancestors + rows +
        # targets×reserve + margin ≤ 0.8×window. Каждая строка чанка учитывается как
        # ПОТЕНЦИАЛЬНАЯ цель (reserve входит в её стоимость) — реальное число целей ≤ числа
        # строк, оценка сверху.
        row_budget = (
            int(_CONTEXT_SHARE * self._window)
            - _SYSTEM_PROMPT_RESERVE - catalog_tokens - _ANCESTORS_RESERVE - _OUTPUT_MARGIN
        )
        if row_budget <= 0:
            raise CatalogTooLargeError(
                f"после справочника (~{catalog_tokens}) на смету не остаётся бюджета"
            )
        row_tokens = self._row_cost  # estimate_tokens(строка) + формат + output_reserve_per_row

        def is_target(i: int) -> bool:
            return tree[i].status in EXPECTED and tree[i].review_status == "unreviewed"

        def commit(i: int, result: NodeMatch) -> None:
            ok = self._estimates.save_node_match_cas(tree[i].id, result, EXPECTED)
            tree[i] = (
                tree[i].with_result(result) if ok else self._estimates.refresh_tree_node(tree[i].id)
            )
            if ok:
                counts[result.status] += 1

        def ctx(i: int) -> AncestorContext:
            return effective_ancestor_context(i, tree, parents)

        def in_failed(i: int) -> bool:
            p: int | None = i
            while p is not None:
                if p in failed_roots:
                    return True
                p = parents[p]
            return False

        def process(chunk: Chunk, max_rows: int) -> None:
            targets = [i for i in chunk.indices if is_target(i)]
            for i in chunk.oversized:
                if i in targets:
                    commit(i, NodeMatch(EstimateRowStatus.ERROR, match_error=ERR_ROW_TOO_LARGE))
            targets = [i for i in targets if i not in chunk.oversized]
            if not targets:
                return
            if in_failed(chunk.root):
                for i in targets:
                    commit(i, NodeMatch(EstimateRowStatus.ERROR, match_error=ERR_ANCESTOR_FAILED))
                return
            # PR 1: pre-call фонд выключен (fund_enabled=False) — контекст считается сразу под вызов
            target_ids = frozenset(tree[i].id for i in targets)
            req = SectionMatchRequest(
                nodes=[tree[i] for i in chunk.indices],
                ancestors=self._ancestors(chunk.root, tree, parents),
                hints=build_hints(chunk.indices, tree, target_ids),
                targets=target_ids, catalog=catalog_list, precedents=[],
            )
            try:
                resp = self._matcher.match_section(req)
            except TransientError as exc:
                failed_roots.add(chunk.root)
                for i in targets:
                    commit(
                        i, NodeMatch(EstimateRowStatus.ERROR, match_error=f"{ERR_TRANSIENT}: {exc}")
                    )
                return
            if resp.truncated:
                half = max_rows // 2
                if half < self._min_rows or len(chunk.indices) <= self._min_rows:
                    for i in targets:
                        commit(i, NodeMatch(EstimateRowStatus.ERROR, match_error=ERR_TRUNCATED))
                    return
                sub = split_sections(
                    [tree[i] for i in chunk.indices], _reindex(parents, chunk.indices),
                    max_rows=half, budget_tokens=row_budget, row_tokens=row_tokens,
                )
                for c in sub:
                    process(_map_back(c, chunk.indices), half)
                return
            by_id: dict[int, dict] = {}
            for item in resp.items:
                nid = item.get("i") if isinstance(item, dict) else None
                if isinstance(nid, int) and nid in target_ids and nid not in by_id:
                    by_id[nid] = item
                elif isinstance(nid, int) and nid in by_id:
                    logger.warning("tree: дубликат вердикта для узла %s — взят первый", nid)
            for i in targets:  # сверху вниз: контекст по принятым вердиктам
                c = ctx(i)
                v = validate_one(by_id.get(tree[i].id), tree[i].id, catalog.keys(), c)
                commit(i, to_node_match(v, c, catalog))

        for chunk in split_sections(
            tree, parents,
            max_rows=self._chunk_rows, budget_tokens=row_budget, row_tokens=row_tokens,
        ):
            process(chunk, self._chunk_rows)
        return counts

    @staticmethod
    def _ancestors(
        root: int, tree: Sequence[TreeNode], parents: Sequence[int | None]
    ) -> list[tuple[TreeNode, tuple[str, bool] | None]]:
        """Путь предков чанка с подсказками hint_for — те же правила доверия, что у контекста."""
        path: list[tuple[TreeNode, tuple[str, bool] | None]] = []
        p = parents[root]
        while p is not None:
            path.append((tree[p], hint_for(tree[p])))
            p = parents[p]
        return list(reversed(path))

    def _row_cost(self, n: TreeNode) -> int:
        """Стоимость строки в бюджете: текст + формат + резерв ответа (строка = потенц. цель)."""
        return estimate_tokens(f"{n.id} | {n.code} | {n.name}") + _ROW_FORMAT_TOKENS + self._reserve


def _reindex(parents: Sequence[int | None], indices: Sequence[int]) -> list[int | None]:
    pos = {g: k for k, g in enumerate(indices)}
    return [pos.get(parents[g]) if parents[g] is not None else None for g in indices]


def _map_back(c: Chunk, indices: Sequence[int]) -> Chunk:
    return Chunk(
        root=indices[c.root], indices=[indices[k] for k in c.indices],
        oversized=[indices[k] for k in c.oversized],
    )
