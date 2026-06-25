"""WorkTypeClassifier через OpenRouter (OpenAI-совместимый /chat/completions).

Дешёвая модель, отдельно от арбитра матчинга. Батч + строгий JSON + фолбэк в UNSURE:
любой сбой/битый JSON/несовпадение длины → весь батч UNSURE, НИКОГДА ORG (асимметрия ошибок).
"""

from __future__ import annotations

import json
import logging

import httpx

from app.domain.entities import NodeToClassify, WorkClass
from app.domain.ports import WorkTypeClassifier
from app.infrastructure.retry import retry_transient

logger = logging.getLogger(__name__)

_REFERER = "https://github.com/zhukovvlad/ciw-tenders"
_TITLE = "CIW Estimate Matcher"
_MAX_TOKENS = 2048  # батч возвращает JSON-массив из N объектов

SYSTEM_PROMPT = (
    "Ты классифицируешь строки строительной сметы. Для каждого имени реши, "
    "является ли оно ОБОЗНАЧЕНИЕМ ВИДА СТРОИТЕЛЬНЫХ РАБОТ — где угодно в строке, "
    "независимо от порядка слов.\n"
    "- Если имя — ТОЛЬКО метка этапа/очереди/корпуса/объекта (организационный "
    "каркас) → класс \"org\".\n"
    "- Если имя называет работу, пусть даже привязанную к этапу/корпусу → \"work\".\n"
    "- Если по имени и предкам уверенно решить нельзя → \"unsure\".\n"
    "При сомнении выбирай \"work\" или \"unsure\", НЕ \"org\".\n"
    "Ответ — СТРОГО JSON-массив объектов {\"i\": <индекс>, \"class\": "
    "\"work|org|unsure\"} без преамбулы и markdown."
)

_CLASS_BY_NAME = {"work": WorkClass.WORK, "org": WorkClass.ORG, "unsure": WorkClass.UNSURE}


class _BodyError(Exception):
    """Ошибка в теле ответа OpenRouter (HTTP 200, но error/нет choices)."""

    def __init__(self, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.transient = transient


def build_batch_prompt(items: list[NodeToClassify]) -> str:
    lines = []
    for i, item in enumerate(items):
        ctx = " / ".join(item.ancestors) if item.ancestors else "(корень)"
        lines.append(f"{i}. имя: {item.name!r} | предки: {ctx}")
    return "Классифицируй:\n" + "\n".join(lines)


def _strip_fences(text: str) -> str:
    """Снять markdown-ограждение ```json … ``` — модель иногда оборачивает вопреки промпту.

    Закрывающую рамку ищем как ПОСЛЕДНЕЕ вхождение ``` (модель может дописать
    комментарий после рамки) — иначе сырой ``` утёк бы в json.loads → весь батч UNSURE.
    """
    s = text.strip()
    if not s.startswith("```"):
        return s
    s = s[3:]
    if s[:4].lower() == "json":
        s = s[4:]
    end = s.rfind("```")
    if end != -1:
        s = s[:end]
    return s.strip()


def parse_classifications(text: str, n: int) -> list[WorkClass]:
    """Строгий парс. Любая аномалия (битый JSON, не та длина) → всё UNSURE."""
    try:
        data = json.loads(_strip_fences(text))
    except (json.JSONDecodeError, TypeError):
        return [WorkClass.UNSURE] * n
    if not isinstance(data, list) or len(data) != n:
        return [WorkClass.UNSURE] * n
    out: list[WorkClass] = [WorkClass.UNSURE] * n
    for entry in data:
        if not isinstance(entry, dict):
            continue
        idx = entry.get("i")
        if isinstance(idx, int) and 0 <= idx < n:
            out[idx] = _CLASS_BY_NAME.get(str(entry.get("class")).lower(), WorkClass.UNSURE)
    return out


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429,) or exc.response.status_code >= 500
    if isinstance(exc, _BodyError):
        return exc.transient
    return False


class OpenRouterWorkClassifier(WorkTypeClassifier):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "anthropic/claude-haiku-4.5",
        batch_size: int = 40,
        *,
        client: httpx.Client | None = None,
        timeout_s: float = 30.0,
        retry_budget: int = 3,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._batch_size = batch_size
        self._retry_budget = retry_budget
        self._client = client or httpx.Client(timeout=timeout_s)

    def classify(self, items: list[NodeToClassify]) -> list[WorkClass]:
        out: list[WorkClass] = []
        for start in range(0, len(items), self._batch_size):
            chunk = items[start : start + self._batch_size]
            out.extend(self._classify_chunk(chunk))
        return out

    def _classify_chunk(self, chunk: list[NodeToClassify]) -> list[WorkClass]:
        prompt = build_batch_prompt(chunk)
        try:
            text = retry_transient(
                lambda: self._call(prompt),
                budget=self._retry_budget,
                classify=_is_transient,
            )
        except Exception:  # noqa: BLE001 — фолбэк по асимметрии: сбой → UNSURE, не ORG
            logger.warning("Классификатор: сбой батча (%d имён) → UNSURE", len(chunk))
            return [WorkClass.UNSURE] * len(chunk)
        return parse_classifications(text, len(chunk))

    def _call(self, prompt: str) -> str:
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
                    {"role": "user", "content": prompt},
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
            logger.error("OpenRouter classifier: неожиданная структура ответа: %r", data)
            raise _BodyError(
                f"OpenRouter classifier: неожиданная структура ответа: {exc}",
                transient=False,
            ) from exc
        return content or ""

    @staticmethod
    def _raise_body_error(error: dict) -> None:
        code = error.get("code")
        message = error.get("message", "")
        transient = code == 429 or (isinstance(code, int) and code >= 500)
        if transient:
            logger.warning("OpenRouter classifier транзиентная ошибка в теле: %s", message)
        else:
            logger.error("OpenRouter classifier перманентная ошибка (code=%s): %s", code, message)
        raise _BodyError(f"OpenRouter error (code={code}): {message}", transient=transient)
