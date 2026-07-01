"""Чистые функции золотого фонда решений: нормализация ключа + guard «единственный ответ».

Без БД/AI. Ключ строится поверх уже-org-стрипнутой крошки (embedding_input) — он код-free и
этап-free, поэтому повторяемая работа даёт один ключ независимо от нумерации/этапа.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FundHit:
    """Живое попадание фонда (id + текущие код/имя из каталога — apply-time, без N+1)."""

    article_id: int
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class FundEntry:
    """Запись для upsert при промоушене."""

    cache_key_hash: str
    cache_key: str
    crumb_version: int
    article_id: int
    source_estimate_id: int
    source_row_id: int


def normalize_cache_key(embedding_input: str) -> str:
    """Детерминированная нормализация: регистр + схлопывание пробелов. Версия крошки НЕ внутри
    ключа (хранится отдельной колонкой)."""
    return re.sub(r"\s+", " ", embedding_input.strip().lower())


def cache_key_hash(key: str) -> str:
    """sha256-hex нормализованного ключа — для unique-индекса (TEXT в btree-unique = мина)."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def resolve_fund_decision(live_article_ids: Sequence[int]) -> int | None:
    """Guard «единственный ответ»: ровно одна различная статья среди ЖИВЫХ → она; иначе None
    (0 → промах/только мёртвые; ≥2 различных → конфликт → молчим)."""
    distinct = set(live_article_ids)
    return next(iter(distinct)) if len(distinct) == 1 else None
