"""Реализация LLMMatcher через Anthropic Claude 3.5 Sonnet.

LLM выступает арбитром: из топ-K кандидатов выбирает наиболее подходящую статью
(или сообщает об отсутствии совпадения). Возвращаем индекс — детерминированный парсинг.
"""

from __future__ import annotations

import re

import anthropic
import httpx

from app.domain.entities import ArticleCandidate, TemplateArticle
from app.domain.ports import LLMMatcher
from app.infrastructure.retry import retry_transient

_SYSTEM_PROMPT = (
    "Ты — эксперт по строительным сметам. Тебе дают наименование работы из сметы "
    "и пронумерованный список статей-кандидатов из справочника СМР. "
    "Выбери одну статью, которая точнее всего соответствует работе. "
    "Ответь СТРОГО одним числом — номером кандидата. Если ни один не подходит, ответь 0."
)


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code in (429,) or exc.status_code >= 500
    if isinstance(exc, anthropic.APIConnectionError):
        return True
    return False


class AnthropicLLMMatcher(LLMMatcher):
    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20240620",
        timeout_s: float = 30.0,
        retry_budget: int = 3,
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s)
        self._model = model
        self._retry_budget = retry_budget

    def choose_best(
        self, query: str, candidates: list[ArticleCandidate]
    ) -> TemplateArticle | None:
        if not candidates:
            return None

        listing = "\n".join(
            f"{i + 1}. [{c.article.article_code}] {c.article.name}"
            for i, c in enumerate(candidates)
        )
        user_prompt = f'Работа из сметы: "{query}"\n\nКандидаты:\n{listing}'

        def _call_llm() -> str:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=16,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text if response.content else "0"

        text = retry_transient(_call_llm, budget=self._retry_budget, classify=_is_transient)

        # Structural validation: must be parseable integer
        match = re.search(r"\d+", text)
        if not match:
            # Non-JSON / unparseable response — structural defect, decline without retry
            return None
        choice = int(match.group())

        # Structural validation: chosen index must be within candidates range
        if not (1 <= choice <= len(candidates)):
            return None
        return candidates[choice - 1].article
