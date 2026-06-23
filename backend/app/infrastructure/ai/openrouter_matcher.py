"""LLMMatcher через OpenRouter (OpenAI-совместимый /chat/completions).

Семантика промпта/парсинга — из llm_matching_common (та же, что у Anthropic).
Ошибка в теле ответа (HTTP 200): транзиент → TransientError (ретрай), перманент
(невалидный слаг/auth/...) → громкий не-транзиентный _BodyError (всплывёт до partial_error).
"""

from __future__ import annotations

import logging

import httpx

from app.domain.entities import ArticleCandidate, TemplateArticle
from app.domain.ports import LLMMatcher
from app.infrastructure.ai.llm_matching_common import (
    SYSTEM_PROMPT,
    build_user_prompt,
    parse_choice,
)
from app.infrastructure.retry import retry_transient

logger = logging.getLogger(__name__)

_MAX_TOKENS = 16
_REFERER = "https://github.com/zhukovvlad/ciw-tenders"
_TITLE = "CIW Estimate Matcher"


class _BodyError(Exception):
    """Ошибка в теле ответа OpenRouter (HTTP 200, но error/нет choices)."""

    def __init__(self, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.transient = transient


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429,) or exc.response.status_code >= 500
    if isinstance(exc, _BodyError):
        return exc.transient
    return False


class OpenRouterLLMMatcher(LLMMatcher):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "anthropic/claude-sonnet-4.6",
        *,
        client: httpx.Client | None = None,
        timeout_s: float = 30.0,
        retry_budget: int = 3,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._retry_budget = retry_budget
        self._client = client or httpx.Client(timeout=timeout_s)

    def choose_best(
        self, query: str, candidates: list[ArticleCandidate]
    ) -> TemplateArticle | None:
        if not candidates:
            return None
        user_prompt = build_user_prompt(query, candidates)
        text = retry_transient(
            lambda: self._call(user_prompt),
            budget=self._retry_budget,
            classify=_is_transient,
        )
        return parse_choice(text, candidates)

    def _call(self, user_prompt: str) -> str:
        resp = self._client.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": _REFERER,
                "X-Title": _TITLE,
            },
            json={
                "model": self._model,
                "temperature": 0,
                "max_tokens": _MAX_TOKENS,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        error = data.get("error")
        if error is not None:
            self._raise_body_error(error)
        choices = data.get("choices")
        if not choices:
            raise _BodyError("OpenRouter: ответ без choices", transient=True)
        try:
            content = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            # choices есть, но структура неожиданная — не глотать голым KeyError,
            # привести к перманентному _BodyError с логом (как error-ветка)
            logger.error("OpenRouter: неожиданная структура ответа: %r", data)
            raise _BodyError(
                f"OpenRouter: неожиданная структура ответа: {exc}", transient=False
            ) from exc
        return content or "0"

    @staticmethod
    def _raise_body_error(error: dict) -> None:
        code = error.get("code")
        message = error.get("message", "")
        transient = code == 429 or (isinstance(code, int) and code >= 500)
        if transient:
            logger.warning("OpenRouter транзиентная ошибка в теле: %s", message)
        else:
            logger.error("OpenRouter перманентная ошибка (code=%s): %s", code, message)
        raise _BodyError(f"OpenRouter error (code={code}): {message}", transient=transient)
