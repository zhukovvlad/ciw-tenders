"""LLMMatcher через прямой Anthropic SDK. Семантика промпта/парсинга — из llm_matching_common."""

from __future__ import annotations

import anthropic
import httpx

from app.domain.entities import ArticleCandidate, TemplateArticle
from app.domain.ports import LLMMatcher
from app.infrastructure.ai.llm_matching_common import (
    SYSTEM_PROMPT,
    build_user_prompt,
    parse_choice,
)
from app.infrastructure.retry import retry_transient


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
        model: str = "claude-sonnet-4-6",
        timeout_s: float = 30.0,
        retry_budget: int = 3,
        *,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self._client = client or anthropic.Anthropic(api_key=api_key, timeout=timeout_s)
        self._model = model
        self._retry_budget = retry_budget

    def choose_best(
        self, query: str, candidates: list[ArticleCandidate]
    ) -> TemplateArticle | None:
        if not candidates:
            return None
        user_prompt = build_user_prompt(query, candidates)

        def _call_llm() -> str:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=16,
                temperature=0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text if response.content else "0"

        text = retry_transient(_call_llm, budget=self._retry_budget, classify=_is_transient)
        return parse_choice(text, candidates)
