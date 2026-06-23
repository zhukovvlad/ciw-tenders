"""Общая семантика LLM-арбитра матчинга — едина для всех провайдеров.

От парсинга ответа зависят «честный score» и трактовка отказа, поэтому логика ОДНА:
адаптеры провайдеров отвечают только за сетевой вызов, не за смысл ответа.
"""

from __future__ import annotations

import logging
import re

from app.domain.entities import ArticleCandidate, TemplateArticle

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Ты — эксперт по строительным сметам. Тебе дают наименование работы из сметы "
    "и пронумерованный список статей-кандидатов из справочника СМР. "
    "Выбери одну статью, которая точнее всего соответствует работе. "
    "Ответь СТРОГО одним числом — НОМЕРОМ СТРОКИ из списка (1, 2, 3...), а НЕ кодом статьи. "
    "Если ни один кандидат не подходит, ответь 0. Никаких слов — только число."
)


def build_user_prompt(query: str, candidates: list[ArticleCandidate]) -> str:
    """Листинг кандидатов БЕЗ кода статьи.

    Выбор по имени — код провоцирует echo кода вместо номера.
    """
    listing = "\n".join(f"{i + 1}. {c.article.name}" for i, c in enumerate(candidates))
    return f'Работа из сметы: "{query}"\n\nКандидаты:\n{listing}'


def parse_choice(text: str, candidates: list[ArticleCandidate]) -> TemplateArticle | None:
    """Первый целочисленный токен ответа → кандидат. 0/нет числа/вне диапазона → None (отказ).

    `0` отсекается ДО индексации (иначе candidates[-1] на choice=0 — ложный матч).
    Знак учитывается: «-1» парсится как отрицательное → вне диапазона → None, а не candidates[0].
    Warning только на непустой-не-«0»-непарсящийся ответ (легитимный отказ ≠ сбой формата).
    """
    match = re.search(r"-?\d+", text)
    if match is None:
        if text.strip():
            logger.warning("LLM-арбитр вернул нечитаемый ответ: %r", text)
        return None
    choice = int(match.group())
    if choice == 0:
        return None  # легитимный отказ — без warning
    if not 1 <= choice <= len(candidates):
        logger.warning("LLM-арбитр: индекс вне диапазона 1..%d: %r", len(candidates), text)
        return None
    return candidates[choice - 1].article
