"""Чистый домен бенчмарка: нормализация gold-кода/имени и подсказка класса узла."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.classification import contains_org_token, has_work_word

_CODE_LINE = re.compile(r"^\((.*?)\)\s*(.*)$", re.DOTALL)


class BenchmarkKind(StrEnum):
    MATCHABLE = "matchable"      # есть эталонная статья — меряем top-1/top-3
    STRUCTURAL = "structural"    # оргкаркас — пайплайн должен исключить
    NO_ARTICLE = "no_article"    # работа без статьи в справочнике — оставить, не сматчить


def norm_code(raw: str) -> str:
    return re.sub(r"\s+", "", raw).strip(".")


def norm_name(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.replace("\xa0", " ")).strip().lower()


def parse_gold_cell(cell: str | None) -> tuple[str | None, str | None]:
    """`(6.3.1) Name` → ('6.3.1', 'Name'); пусто/мусор → (None, None)."""
    if cell is None:
        return (None, None)
    match = _CODE_LINE.match(str(cell).strip())
    if match is None:
        return (None, None)
    code = norm_code(match.group(1))
    # Снимок имени — регистр СОХРАНЯЕМ (читаемость + UI Спеки B), НЕ зовём norm_name.
    # \s покрывает \xa0, так что отличие от norm_name только в .lower(); лоуэркейс
    # применяется к обеим сторонам лишь при сравнении article_renamed.
    name = re.sub(r"\s+", " ", match.group(2)).strip()
    if not code or not all(seg.isdigit() for seg in code.split(".")):
        return (None, None)
    return (code, name or None)


def suggest_kind(cell: str | None, node_name: str) -> BenchmarkKind:
    """Гейт-подсказка: статья задана → matchable; пусто+(орг|нет головы) → structural;
    пусто+голова без орг → no_article (требует подтверждения человеком)."""
    code, _ = parse_gold_cell(cell)
    if code is not None:
        return BenchmarkKind.MATCHABLE
    if contains_org_token(node_name) or not has_work_word(node_name):
        return BenchmarkKind.STRUCTURAL
    return BenchmarkKind.NO_ARTICLE


@dataclass(frozen=True, slots=True)
class NodeOutcome:
    expected_kind: BenchmarkKind
    expected_code: str | None
    kept: bool
    status: str
    matched_code: str | None
    top3_codes: list[str] = field(default_factory=list)
    catalog_has_code: bool = True
    # текущее имя статьи (norm) или None, если совпадает/нет кода
    catalog_name_norm: str | None = None


@dataclass(frozen=True, slots=True)
class EvalReport:
    # Группа A (только structural+matchable)
    a_tn: int
    a_fp: int
    a_fn: int
    a_tp: int
    # Группа A′ (no_article) — бакеты исчерпывающие
    no_article_total: int
    no_article_correct_no_match: int
    no_article_wrong_confident: int
    no_article_needs_review: int
    # no_article с прочим статусом (excluded/error) — иначе тихо выпадал из разбивки
    no_article_other: int
    # Группа B (только matchable, kept, код есть в каталоге, НЕ error)
    b_total: int
    b_top1_hits: int
    b_top3_hits: int
    b_error: int  # matchable+kept+в каталоге, но status='error' — вне знаменателя B
    # Дрейф каталога
    gold_not_in_catalog: int
    article_renamed: int


def _is_renamed(o: NodeOutcome) -> bool:
    return (
        o.expected_kind is BenchmarkKind.MATCHABLE
        and o.catalog_has_code
        and o.catalog_name_norm is not None
    )


def compute_metrics(
    outcomes: Sequence[NodeOutcome], *, confident_statuses: tuple[str, ...] = ("confident",)
) -> EvalReport:
    a_tn = a_fp = a_fn = a_tp = 0
    na_total = na_ok = na_wrong = na_review = na_other = 0
    b_total = b_top1 = b_top3 = b_error = 0
    not_in_cat = renamed = 0

    for o in outcomes:
        if o.expected_kind is BenchmarkKind.STRUCTURAL:
            if o.kept:
                a_fp += 1
            else:
                a_tn += 1
        elif o.expected_kind is BenchmarkKind.MATCHABLE:
            if o.kept:
                a_tp += 1
            else:
                a_fn += 1
            if _is_renamed(o):
                renamed += 1
            if not o.catalog_has_code:
                not_in_cat += 1
            elif o.kept:
                if o.status == "error":
                    b_error += 1   # транзиентная AI-ошибка — не промах, вне знаменателя
                else:
                    b_total += 1
                    if o.matched_code == o.expected_code:
                        b_top1 += 1
                    if o.expected_code in o.top3_codes:
                        b_top3 += 1
        elif o.expected_kind is BenchmarkKind.NO_ARTICLE:
            na_total += 1
            if o.status == "no_match":
                na_ok += 1
            elif o.status in confident_statuses:
                na_wrong += 1
            elif o.status == "needs_review":
                na_review += 1
            else:
                na_other += 1

    return EvalReport(
        a_tn=a_tn, a_fp=a_fp, a_fn=a_fn, a_tp=a_tp,
        no_article_total=na_total,
        no_article_correct_no_match=na_ok,
        no_article_wrong_confident=na_wrong,
        no_article_needs_review=na_review,
        no_article_other=na_other,
        b_total=b_total, b_top1_hits=b_top1, b_top3_hits=b_top3, b_error=b_error,
        gold_not_in_catalog=not_in_cat, article_renamed=renamed,
    )
