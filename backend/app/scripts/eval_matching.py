"""Оффлайн-метрика матчинга: прогон бенчмарка через реальный пайплайн.

Запуск: uv run python -m app.scripts.eval_matching [--benchmark <name>] [--report <csv>] [--keep]
Требует проэмбеженный справочник и валидный backend/.env.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import tempfile

from app.api.deps import build_estimate_matching_service
from app.core.logging_config import setup_logging
from app.domain.benchmark import BenchmarkKind, NodeOutcome, compute_metrics, norm_name
from app.domain.entities import BenchmarkNodeSeed, Estimate, NewEstimate
from app.infrastructure.db.article_repository import SqlAlchemyArticleRepository
from app.infrastructure.db.benchmark_repository import SqlAlchemyBenchmarkRepository
from app.infrastructure.db.estimate_repository import SqlAlchemyEstimateRepository
from app.infrastructure.db.models import UserModel
from app.infrastructure.db.session import SessionLocal
from app.services.benchmark_reconstruct import reconstruct_nodes

logger = logging.getLogger(__name__)


def _pick_benchmark(repo: SqlAlchemyBenchmarkRepository, name: str | None) -> int:
    items = repo.list_benchmarks()
    if not items:
        raise SystemExit("Нет бенчмарков. Сначала: just benchmark-seed gold=\"...\"")
    if name is not None:
        bid = repo.get_by_name(name)
        if bid is None:
            raise SystemExit(f"Бенчмарк '{name}' не найден. Есть: {[n for _, n in items]}")
        return bid
    if len(items) > 1:
        raise SystemExit(f"Бенчмарков несколько, укажите --benchmark: {[n for _, n in items]}")
    return items[0][0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", default=None)
    parser.add_argument(
        "--report", default=os.path.join(tempfile.gettempdir(), "eval_matching.csv")
    )
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    setup_logging()  # конвенция CLI; заодно форматирует логи пайплайна (per-estimate
                     # summary + латентность/попытки AI-вызовов) во время прогона.
    session = SessionLocal()
    try:
        articles = SqlAlchemyArticleRepository(session)
        total, pending = articles.matching_readiness()
        if total == 0 or pending > 0:
            raise SystemExit(
                f"Справочник не готов (total={total}, pending={pending}). "
                f"Загрузите шаблон и прогоните эмбеддинг-воркер."
            )

        bench_repo = SqlAlchemyBenchmarkRepository(session)
        benchmark_id = _pick_benchmark(bench_repo, args.benchmark)
        seeds = bench_repo.fetch_nodes(benchmark_id)

        user_id = session.query(UserModel.id).order_by(UserModel.id).limit(1).scalar()
        if user_id is None:
            raise SystemExit("Нет пользователей. Сначала: just create-admin")

        estimates = SqlAlchemyEstimateRepository(session)
        nodes = reconstruct_nodes(seeds)
        estimate = estimates.create(
            NewEstimate(user_id=user_id, filename="__benchmark_eval__", original_object_key="eval"),
            nodes,
        )
        try:
            build_estimate_matching_service(session).match_estimate(estimate.id)
            stored = estimates.get(estimate.id, user_id, is_admin=True)
            _report(seeds, stored, articles, args.report)
        finally:
            if not args.keep:
                estimates.delete(estimate.id, user_id, is_admin=True)
    finally:
        session.close()


def _report(
    seeds: list[BenchmarkNodeSeed],
    stored: Estimate,
    articles: SqlAlchemyArticleRepository,
    report_path: str,
) -> None:
    # Ключ — source_index, НЕ code: коды раздела дублируются между этапами
    # (3.1.4.1 встречается дважды как разные строки). seed_by_code схлопнул бы дубли
    # и приписал обоим эталон одного — тот же провал, что cls_by_code в org-filter.
    # source_index уникален на строку и протянут seed → EstimateNode → estimate_rows → DTO.
    seed_by_index = {s.source_index: s for s in seeds}
    outcomes: list[NodeOutcome] = []
    rows_csv: list[dict] = []
    for row in stored.rows:
        seed = seed_by_index.get(row.source_index)
        if seed is None:
            continue
        kind = BenchmarkKind(seed.expected_kind)
        top3 = [c.code for c in row.candidates]
        catalog_has = catalog_name_norm = None
        if kind is BenchmarkKind.MATCHABLE and seed.expected_article_code:
            art = articles.get_by_code(seed.expected_article_code)
            catalog_has = art is not None
            if art is not None and seed.expected_article_name is not None:
                if norm_name(art.name) != norm_name(seed.expected_article_name):
                    catalog_name_norm = norm_name(art.name)
        outcomes.append(
            NodeOutcome(
                expected_kind=kind,
                expected_code=seed.expected_article_code,
                kept=row.status != "excluded",
                status=row.status,
                matched_code=row.matched_code,
                top3_codes=top3,
                catalog_has_code=bool(catalog_has) if catalog_has is not None else True,
                catalog_name_norm=catalog_name_norm,
            )
        )
        rows_csv.append({
            "code": row.code, "name": row.name, "expected_kind": seed.expected_kind,
            "gold_code": seed.expected_article_code or "",
            "gold_name": seed.expected_article_name or "",
            "kept": row.status != "excluded", "status": row.status,
            "chosen_code": row.matched_code or "", "top3_codes": "|".join(top3),
            "top1_hit": row.matched_code == seed.expected_article_code,
            "top3_hit": (seed.expected_article_code in top3) if seed.expected_article_code else "",
            "article_renamed": catalog_name_norm is not None,
        })

    r = compute_metrics(outcomes)
    print("\n=== Группа A (классификация) ===")
    print(f"TN={r.a_tn}  FP={r.a_fp}  FN={r.a_fn} (молчаливый пропуск работы!)  TP={r.a_tp}")
    print("\n=== Группа A' (no_article) ===")
    print(f"всего={r.no_article_total}  → no_match={r.no_article_correct_no_match}  "
          f"needs_review={r.no_article_needs_review}  "
          f"ошибочный уверенный матч={r.no_article_wrong_confident}")
    print("\n=== Группа B (матчинг, matchable) ===")
    denom = r.b_total or 1
    print(f"узлов={r.b_total}  top-1={r.b_top1_hits} ({100*r.b_top1_hits/denom:.1f}%)  "
          f"top-3 retrieval={r.b_top3_hits} ({100*r.b_top3_hits/denom:.1f}%)  "
          f"[error вне знаменателя: {r.b_error}]")
    print(
        f"\nдрейф: gold_not_in_catalog={r.gold_not_in_catalog}  "
        f"article_renamed={r.article_renamed}"
    )

    if not rows_csv:
        logger.warning(
            "Ни одна строка результата не сопоставилась с gold по source_index — "
            "проверь, что source_index протянут seed→EstimateNode→estimate_rows."
        )
        return

    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows_csv[0].keys()))
        writer.writeheader()
        writer.writerows(rows_csv)
    print(f"\nCSV-детализация: {report_path}")


if __name__ == "__main__":
    main()
