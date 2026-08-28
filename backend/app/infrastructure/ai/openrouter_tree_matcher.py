"""TreeMatcher через OpenRouter chat/completions (спека §5.1)."""

from __future__ import annotations

import logging

import httpx

from app.domain.entities import SectionMatchRequest, SectionMatchResponse
from app.domain.ports import TreeMatcher
from app.infrastructure.ai._instrumented import instrumented_call
from app.infrastructure.ai.tree_prompt import (
    SYSTEM_PROMPT,
    build_user_prompt,
    parse_verdicts,
    render_catalog,
)

logger = logging.getLogger(__name__)
_REFERER = "https://github.com/zhukovvlad/ciw-tenders"
_TITLE = "CIW Tree Matcher"
_OUTPUT_MARGIN = 512


class _BodyError(Exception):
    """Ошибка в теле ответа OpenRouter (HTTP 200, но error/нет choices)."""

    def __init__(self, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.transient = transient


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, _BodyError) and exc.transient


class OpenRouterTreeMatcher(TreeMatcher):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "anthropic/claude-sonnet-5",
        *,
        reasoning_effort: str = "low",
        output_reserve_per_row: int = 48,
        client: httpx.Client | None = None,
        timeout_s: float = 300.0,
        retry_budget: int = 3,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._effort = reasoning_effort
        self._reserve = output_reserve_per_row
        self._budget = retry_budget
        self._client = client or httpx.Client(timeout=timeout_s)

    def match_section(self, req: SectionMatchRequest) -> SectionMatchResponse:
        # справочник — в system-блоке с cache_control: одинаков для всех чанков сметы
        system_text = f"{SYSTEM_PROMPT}\n\nСПРАВОЧНИК:\n{render_catalog(req.catalog)}"
        user_text = build_user_prompt(req, include_catalog=False)
        max_tokens = len(req.targets) * self._reserve + _OUTPUT_MARGIN
        return instrumented_call(
            provider="openrouter",
            model=self._model,
            fn=lambda: self._call(system_text, user_text, max_tokens),
            budget=self._budget,
            classify=_is_transient,
        )

    def _call(self, system_text: str, user_text: str, max_tokens: int) -> SectionMatchResponse:
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
                "max_tokens": max_tokens,
                "reasoning": {"effort": self._effort},
                "messages": [
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "text",
                                "text": system_text,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                    },
                    {"role": "user", "content": user_text},
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if (error := data.get("error")) is not None:
            code = error.get("code")
            transient = code == 429 or (isinstance(code, int) and code >= 500)
            raise _BodyError(
                f"OpenRouter error (code={code}): {error.get('message', '')}",
                transient=transient,
            )
        choices = data.get("choices")
        if not choices:
            raise _BodyError("OpenRouter: ответ без choices", transient=True)
        try:
            content = choices[0]["message"]["content"] or ""
            finish = choices[0].get("finish_reason")
        except (KeyError, IndexError, TypeError) as exc:
            raise _BodyError(
                f"OpenRouter: неожиданная структура ответа: {exc}", transient=False
            ) from exc
        if finish == "length":
            logger.warning(
                "tree: ответ обрезан по max_tokens=%d", max_tokens, extra={"model": self._model}
            )
            return SectionMatchResponse(items=[], truncated=True)
        items = parse_verdicts(content)
        if items is None:
            logger.warning("tree: нечитаемый JSON от модели (%d символов)", len(content))
            return SectionMatchResponse(items=[], truncated=False)
        return SectionMatchResponse(items=items, truncated=False)
