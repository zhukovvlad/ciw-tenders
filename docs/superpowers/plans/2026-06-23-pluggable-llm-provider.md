# Pluggable LLM Provider (арбитр матчинга) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать LLM-арбитр матчинга переключаемым по конфигу (OpenRouter — дефолт, Anthropic — опция), с единой семантикой парсинга/промпта во всех провайдерах и fail-fast валидацией конфига.

**Architecture:** Порт `LLMMatcher` не меняется. Общий модуль `llm_matching_common` несёт системный промпт + построение запроса + парсинг ответа (от него зависят «честный score» и трактовка отказа — он ОДИН). Тонкие адаптеры на провайдера (`AnthropicLLMMatcher` рефактор, `OpenRouterLLMMatcher` новый) отвечают только за сетевой вызов и классификацию ошибок. Фабрика `get_llm_matcher()` строит адаптер по `settings.llm_provider`; валидация (провайдер/ключ/депрекация) — в `@model_validator` конфига (fail-fast при инстанцировании `Settings`).

**Tech Stack:** Python 3.11+, pydantic-settings, httpx, anthropic SDK, pytest.

**Спека:** [docs/superpowers/specs/2026-06-23-pluggable-llm-provider-design.md](../specs/2026-06-23-pluggable-llm-provider-design.md)

## Global Constraints

- **Clean Architecture:** `api → services → domain ← infrastructure`. Домен (`entities`/`errors`/`ports`) без импортов FastAPI/SQLAlchemy/SDK/Celery. Адаптеры провайдеров — только в `infrastructure/ai/`. Порт `LLMMatcher.choose_best(query, candidates) -> TemplateArticle | None` НЕ меняется.
- **ruff:** line-length 100, `target py311`, `from __future__ import annotations` в каждом модуле, type hints обязательны. `cd backend && uv run ruff check .` перед коммитом.
- **Тесты не ходят в сеть/реальную БД/AI:** инъекция фейкового `httpx.Client` / фейкового anthropic-клиента; для конфига — `monkeypatch` env. `conftest` уже кладёт `OPENROUTER_API_KEY`/`ANTHROPIC_API_KEY`/`DATABASE_URL` в `os.environ`.
- **Команды из `backend/`:** `cd backend && uv run pytest ...`. Кириллица в stdout → `PYTHONIOENCODING=utf-8`.
- **Зависимости — только `uv add`** (новых здесь НЕ нужно: `httpx`/`anthropic` уже есть).
- **Дефолт провайдера — `openrouter`** (переиспользует `OPENROUTER_API_KEY` эмбеддера, новый ключ не нужен).
- **Только обычные chat-модели** (малый `max_tokens`); reasoning вне объёма.
- **Вне объёма:** эмбеддер, Google-адаптер, любые правки SP3.
- **Перед мерджем (человек):** сверить актуальный слаг `anthropic/claude-3.5-sonnet` на стороне OpenRouter.

## File Structure

- `backend/app/infrastructure/ai/llm_matching_common.py` (create) — `SYSTEM_PROMPT`, `build_user_prompt`, `parse_choice`.
- `backend/app/infrastructure/ai/anthropic_matcher.py` (modify) — перевод на common + `temperature=0` + инъекция клиента.
- `backend/app/infrastructure/ai/openrouter_matcher.py` (create) — `OpenRouterLLMMatcher`.
- `backend/app/core/config.py` (modify) — `llm_provider`, per-provider модели, `openrouter_base_url`, депрекация `llm_model`, `@model_validator`.
- `backend/app/api/deps.py` (modify) — `get_llm_matcher()` ветвится по провайдеру.
- `backend/.env.example` (modify) — `LLM_PROVIDER` + per-provider модели + `OPENROUTER_BASE_URL` вместо `LLM_MODEL`.
- Tests (create): `test_llm_matching_common.py`, `test_openrouter_matcher.py`, `test_anthropic_matcher.py`; (modify) `test_config.py`; (create) `test_llm_matcher_factory.py`.

---

## Task 1: Общий модуль `llm_matching_common`

**Files:**
- Create: `backend/app/infrastructure/ai/llm_matching_common.py`
- Test: `backend/tests/test_llm_matching_common.py`

**Interfaces:**
- Consumes: `ArticleCandidate`, `TemplateArticle` из `app.domain.entities` (`ArticleCandidate.article: TemplateArticle`, `.score: float`; `TemplateArticle.name`, `.article_code`, `.id`).
- Produces: `SYSTEM_PROMPT: str`; `build_user_prompt(query: str, candidates: list[ArticleCandidate]) -> str`; `parse_choice(text: str, candidates: list[ArticleCandidate]) -> TemplateArticle | None`.

- [ ] **Step 1: Failing-тест**

Create `backend/tests/test_llm_matching_common.py`:

```python
from __future__ import annotations

import logging

from app.domain.entities import ArticleCandidate, TemplateArticle
from app.infrastructure.ai.llm_matching_common import (
    SYSTEM_PROMPT,
    build_user_prompt,
    parse_choice,
)


def _cand(aid: int, code: str, name: str, score: float = 0.5) -> ArticleCandidate:
    return ArticleCandidate(
        TemplateArticle(id=aid, article_code=code, name=name, embedding_input=f"ei {code}"),
        score,
    )


def _three() -> list[ArticleCandidate]:
    return [_cand(1, "08.03.01", "Кладка"), _cand(2, "08.03.02", "Штукатурка"), _cand(3, "08.03.03", "Окраска")]


def test_build_user_prompt_lists_names_without_code() -> None:
    prompt = build_user_prompt("кладка кирпича", _three())
    assert "1. Кладка" in prompt and "2. Штукатурка" in prompt
    assert "08.03.01" not in prompt  # код НЕ утекает в листинг


def test_system_prompt_requires_row_number_and_refusal_channel() -> None:
    assert "0" in SYSTEM_PROMPT  # канал отказа задан


def test_plain_number_picks_candidate() -> None:
    assert parse_choice("2", _three()).article_code == "08.03.02"


def test_wrapped_answer_picks_candidate() -> None:
    assert parse_choice("The best match is option 2.", _three()).article_code == "08.03.02"


def test_zero_is_refusal_not_last_candidate() -> None:
    # off-by-one guard: "0" → None, НЕ candidates[-1]
    assert parse_choice("0", _three()) is None


def test_zero_does_not_warn(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        assert parse_choice("0", _three()) is None
    assert caplog.records == []  # легитимный отказ ≠ сбой формата


def test_code_like_answer_out_of_range_is_none(caplog) -> None:
    # модель вернула код "08.03.01" при top_k=3 → первый int 8 → вне диапазона → None
    with caplog.at_level(logging.WARNING):
        assert parse_choice("08.03.01", _three()) is None
    assert caplog.records  # это сбой формата → warning


def test_garbage_is_none_with_warning(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        assert parse_choice("не знаю", _three()) is None
    assert caplog.records


def test_empty_is_none_without_warning(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        assert parse_choice("", _three()) is None
    assert caplog.records == []
```

- [ ] **Step 2: Запустить — падает**

Run: `cd backend && uv run pytest tests/test_llm_matching_common.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реализовать модуль**

Create `backend/app/infrastructure/ai/llm_matching_common.py`:

```python
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
    """Листинг кандидатов БЕЗ кода статьи: выбор по имени, код провоцирует echo кода вместо номера."""
    listing = "\n".join(f"{i + 1}. {c.article.name}" for i, c in enumerate(candidates))
    return f'Работа из сметы: "{query}"\n\nКандидаты:\n{listing}'


def parse_choice(text: str, candidates: list[ArticleCandidate]) -> TemplateArticle | None:
    """Первый целочисленный токен ответа → кандидат. 0/нет числа/вне диапазона → None (отказ).

    `0` отсекается ДО индексации (иначе candidates[-1] на choice=0 — ложный матч).
    Warning только на непустой-не-«0»-непарсящийся ответ (легитимный отказ ≠ сбой формата).
    """
    match = re.search(r"\d+", text)
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
```

- [ ] **Step 4: Запустить — зелёный + ruff**

Run: `cd backend && uv run pytest tests/test_llm_matching_common.py -v && uv run ruff check app/infrastructure/ai/llm_matching_common.py tests/test_llm_matching_common.py`
Expected: PASS, ruff чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/ai/llm_matching_common.py backend/tests/test_llm_matching_common.py
git commit -m "feat(matching): общий llm_matching_common (промпт без кода, parse_choice с off-by-one guard)"
```

---

## Task 2: Рефактор `AnthropicLLMMatcher` на common + `temperature=0` + инъекция клиента

**Files:**
- Modify: `backend/app/infrastructure/ai/anthropic_matcher.py`
- Test: `backend/tests/test_anthropic_matcher.py`

**Interfaces:**
- Consumes: `SYSTEM_PROMPT`, `build_user_prompt`, `parse_choice` (Task 1); `retry_transient`; `LLMMatcher` порт.
- Produces: `AnthropicLLMMatcher(api_key, model="claude-3-5-sonnet-20240620", timeout_s=30.0, retry_budget=3, *, client=None)`; `choose_best(query, candidates) -> TemplateArticle | None`.

- [ ] **Step 1: Failing-тест** (инъекция фейкового anthropic-клиента)

Create `backend/tests/test_anthropic_matcher.py`:

```python
from __future__ import annotations

from app.domain.entities import ArticleCandidate, TemplateArticle
from app.infrastructure.ai.anthropic_matcher import AnthropicLLMMatcher


def _cand(aid: int, code: str, name: str) -> ArticleCandidate:
    return ArticleCandidate(
        TemplateArticle(id=aid, article_code=code, name=name, embedding_input=f"ei {code}"), 0.5
    )


class _FakeContent:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [_FakeContent(text)]


class _FakeMessages:
    def __init__(self, text: str) -> None:
        self._text = text
        self.kwargs: dict | None = None

    def create(self, **kwargs) -> _FakeResponse:
        self.kwargs = kwargs
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, text: str) -> None:
        self.messages = _FakeMessages(text)


def test_picks_candidate_and_sets_temperature_zero() -> None:
    client = _FakeClient("2")
    matcher = AnthropicLLMMatcher(api_key="x", client=client)
    cands = [_cand(1, "1.1", "Кладка"), _cand(2, "1.2", "Штукатурка")]
    result = matcher.choose_best("штукатурка", cands)
    assert result.article_code == "1.2"
    assert client.messages.kwargs["temperature"] == 0  # детерминизм


def test_empty_candidates_returns_none() -> None:
    assert AnthropicLLMMatcher(api_key="x", client=_FakeClient("1")).choose_best("q", []) is None


def test_refusal_zero_is_none() -> None:
    matcher = AnthropicLLMMatcher(api_key="x", client=_FakeClient("0"))
    assert matcher.choose_best("q", [_cand(1, "1.1", "X")]) is None
```

- [ ] **Step 2: Запустить — падает**

Run: `cd backend && uv run pytest tests/test_anthropic_matcher.py -v`
Expected: FAIL (нет параметра `client` / `temperature` не передаётся).

- [ ] **Step 3: Переписать адаптер**

Заменить тело `backend/app/infrastructure/ai/anthropic_matcher.py` на:

```python
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
        model: str = "claude-3-5-sonnet-20240620",
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
```

- [ ] **Step 4: Запустить — зелёный + ruff**

Run: `cd backend && uv run pytest tests/test_anthropic_matcher.py -v && uv run ruff check app/infrastructure/ai/anthropic_matcher.py tests/test_anthropic_matcher.py`
Expected: PASS, ruff чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/ai/anthropic_matcher.py backend/tests/test_anthropic_matcher.py
git commit -m "refactor(matching): AnthropicLLMMatcher на llm_matching_common + temperature=0 + инъекция клиента"
```

---

## Task 3: Новый адаптер `OpenRouterLLMMatcher`

**Files:**
- Create: `backend/app/infrastructure/ai/openrouter_matcher.py`
- Test: `backend/tests/test_openrouter_matcher.py`

**Interfaces:**
- Consumes: `SYSTEM_PROMPT`, `build_user_prompt`, `parse_choice` (Task 1); `retry_transient`; `TransientError`; `LLMMatcher` порт.
- Produces: `OpenRouterLLMMatcher(api_key, base_url="https://openrouter.ai/api/v1", model="anthropic/claude-3.5-sonnet", *, client=None, timeout_s=30.0, retry_budget=3)`; `choose_best(...) -> TemplateArticle | None`; private `_BodyError(message, *, transient: bool)`.

- [ ] **Step 1: Failing-тест** (инъекция фейкового `httpx.Client`)

Create `backend/tests/test_openrouter_matcher.py`:

```python
from __future__ import annotations

import httpx
import pytest

from app.domain.entities import ArticleCandidate, TemplateArticle
from app.domain.errors import TransientError
from app.infrastructure.ai.openrouter_matcher import OpenRouterLLMMatcher, _BodyError


def _cand(aid: int, code: str, name: str) -> ArticleCandidate:
    return ArticleCandidate(
        TemplateArticle(id=aid, article_code=code, name=name, embedding_input=f"ei {code}"), 0.5
    )


def _cands() -> list[ArticleCandidate]:
    return [_cand(1, "1.1", "Кладка"), _cand(2, "1.2", "Штукатурка")]


class _FakeResponse:
    def __init__(self, data: dict) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._data


class _FakeClient:
    def __init__(self, *, data: dict | None = None, exc: Exception | None = None) -> None:
        self._data = data
        self._exc = exc
        self.calls: list[dict] = []

    def post(self, url, headers, json) -> _FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        if self._exc is not None:
            raise self._exc
        return _FakeResponse(self._data or {})


def _ok(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


def test_picks_candidate_sends_headers_and_temperature() -> None:
    client = _FakeClient(data=_ok("2"))
    matcher = OpenRouterLLMMatcher(api_key="k", client=client)
    result = matcher.choose_best("штукатурка", _cands())
    assert result.article_code == "1.2"
    sent = client.calls[0]
    assert sent["headers"]["HTTP-Referer"] and sent["headers"]["X-Title"]
    assert sent["json"]["temperature"] == 0


def test_transport_error_exhausts_to_transient() -> None:
    client = _FakeClient(exc=httpx.ConnectError("boom"))
    matcher = OpenRouterLLMMatcher(api_key="k", client=client, retry_budget=1)
    with pytest.raises(TransientError):
        matcher.choose_best("q", _cands())


def test_body_error_transient_becomes_transient() -> None:
    client = _FakeClient(data={"error": {"code": 429, "message": "rate limited"}})
    matcher = OpenRouterLLMMatcher(api_key="k", client=client, retry_budget=1)
    with pytest.raises(TransientError):
        matcher.choose_best("q", _cands())


def test_body_error_permanent_is_loud_not_transient() -> None:
    client = _FakeClient(data={"error": {"code": 404, "message": "model not found"}})
    matcher = OpenRouterLLMMatcher(api_key="k", client=client, retry_budget=1)
    with pytest.raises(_BodyError) as exc:  # перманент — НЕ TransientError, не None
        matcher.choose_best("q", _cands())
    assert not exc.value.transient and "model not found" in str(exc.value)


def test_empty_candidates_returns_none() -> None:
    assert OpenRouterLLMMatcher(api_key="k", client=_FakeClient(data=_ok("1"))).choose_best("q", []) is None
```

- [ ] **Step 2: Запустить — падает**

Run: `cd backend && uv run pytest tests/test_openrouter_matcher.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реализовать адаптер**

Create `backend/app/infrastructure/ai/openrouter_matcher.py`:

```python
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
        model: str = "anthropic/claude-3.5-sonnet",
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
        return choices[0]["message"]["content"] or "0"

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
```

- [ ] **Step 4: Запустить — зелёный + ruff**

Run: `cd backend && uv run pytest tests/test_openrouter_matcher.py -v && uv run ruff check app/infrastructure/ai/openrouter_matcher.py tests/test_openrouter_matcher.py`
Expected: PASS, ruff чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/ai/openrouter_matcher.py backend/tests/test_openrouter_matcher.py
git commit -m "feat(matching): OpenRouterLLMMatcher (chat/completions, атрибуция, transient/permanent ошибки тела)"
```

---

## Task 4: Конфиг — `llm_provider`, per-provider модели, депрекация `llm_model`, `@model_validator`

**Files:**
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `Settings.llm_provider`, `.openrouter_llm_model`, `.anthropic_llm_model`, `.openrouter_base_url`; `@model_validator` роняет на неизвестном провайдере / отсутствующем ключе / заданном `LLM_MODEL`.

- [ ] **Step 1: Failing-тесты** (валидатор раним через свежий `Settings(_env_file=None)` + `monkeypatch`)

Дописать в `backend/tests/test_config.py`:

```python
def test_llm_provider_defaults_to_openrouter() -> None:
    from app.core.config import Settings

    s = Settings(jwt_secret="x", _env_file=None)  # type: ignore[call-arg]
    assert s.llm_provider == "openrouter"
    assert s.openrouter_llm_model and s.anthropic_llm_model
    assert s.openrouter_base_url == "https://openrouter.ai/api/v1"


def test_unknown_provider_fails(monkeypatch) -> None:
    import pytest
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    with pytest.raises(ValidationError):
        Settings(jwt_secret="x", _env_file=None)  # type: ignore[call-arg]


def test_missing_key_for_provider_fails(monkeypatch) -> None:
    import pytest
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(jwt_secret="x", _env_file=None)  # type: ignore[call-arg]


def test_deprecated_llm_model_fails(monkeypatch) -> None:
    import pytest
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.setenv("LLM_MODEL", "claude-3-5-sonnet-20240620")
    with pytest.raises(ValidationError):
        Settings(jwt_secret="x", _env_file=None)  # type: ignore[call-arg]
```

- [ ] **Step 2: Запустить — падает**

Run: `cd backend && uv run pytest tests/test_config.py -v`
Expected: FAIL (полей/валидатора нет; `LLM_MODEL` молча игнорируется).

- [ ] **Step 3: Изменить конфиг**

В `backend/app/core/config.py` добавить импорт `from pydantic import model_validator` (рядом с `pydantic_settings`). Заменить строку `llm_model: str = "claude-3-5-sonnet-20240620"` на:

```python
    # LLM-арбитр матчинга — переключаемый провайдер.
    llm_provider: str = "openrouter"  # "openrouter" | "anthropic"
    openrouter_llm_model: str = "anthropic/claude-3.5-sonnet"  # слаг OpenRouter (сверить перед мерджем)
    anthropic_llm_model: str = "claude-3-5-sonnet-20240620"    # нативный id Anthropic
    openrouter_base_url: str = "https://openrouter.ai/api/v1"  # только для OpenRouter-матчера
    llm_model: str | None = None  # DEPRECATED: задано → ошибка в валидаторе (см. ниже)
```

В конец класса `Settings` (после `gate_retry_backoff_s`, перед закрытием класса) добавить:

```python
    @model_validator(mode="after")
    def _validate_llm(self) -> Settings:
        if self.llm_model is not None:
            raise ValueError(
                "LLM_MODEL устарел → задайте OPENROUTER_LLM_MODEL и/или ANTHROPIC_LLM_MODEL"
            )
        valid = {"openrouter", "anthropic"}
        if self.llm_provider not in valid:
            raise ValueError(f"LLM_PROVIDER должен быть из {valid}, получено: {self.llm_provider!r}")
        if self.llm_provider == "openrouter" and not self.openrouter_api_key:
            raise ValueError("LLM_PROVIDER=openrouter требует OPENROUTER_API_KEY")
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("LLM_PROVIDER=anthropic требует ANTHROPIC_API_KEY")
        return self
```

> Депрекация ловит `LLM_MODEL` и из окружения, и из `.env`-файла: pydantic заполняет поле `llm_model` из любого источника, валидатор роняет если оно не `None`. Пустую строку ключа считаем отсутствием (`if not ...`).

- [ ] **Step 4: Запустить — зелёный + ruff**

Run: `cd backend && uv run pytest tests/test_config.py -v && uv run ruff check app/core/config.py tests/test_config.py`
Expected: PASS, ruff чисто. (Прочие тесты конфига не сломаны: `conftest` кладёт `OPENROUTER_API_KEY` в env, провайдер по умолчанию openrouter → валидатор проходит.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/tests/test_config.py
git commit -m "feat(config): llm_provider + per-provider модели + fail-fast валидатор (провайдер/ключ/депрекация LLM_MODEL)"
```

---

## Task 5: Фабрика `get_llm_matcher()` по провайдеру + `.env.example` + полный прогон

**Files:**
- Modify: `backend/app/api/deps.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_llm_matcher_factory.py`

**Interfaces:**
- Consumes: `Settings.llm_provider`/`.openrouter_*`/`.anthropic_llm_model` (Task 4); `AnthropicLLMMatcher` (Task 2); `OpenRouterLLMMatcher` (Task 3).
- Produces: `get_llm_matcher() -> LLMMatcher` (адаптер по `settings.llm_provider`).

- [ ] **Step 1: Failing-тест фабрики**

Create `backend/tests/test_llm_matcher_factory.py`:

```python
from __future__ import annotations

from app.api.deps import get_llm_matcher
from app.core.config import get_settings
from app.infrastructure.ai.anthropic_matcher import AnthropicLLMMatcher
from app.infrastructure.ai.openrouter_matcher import OpenRouterLLMMatcher


def _reset_caches() -> None:
    get_settings.cache_clear()
    get_llm_matcher.cache_clear()


def test_factory_openrouter(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    _reset_caches()
    try:
        assert isinstance(get_llm_matcher(), OpenRouterLLMMatcher)
    finally:
        _reset_caches()


def test_factory_anthropic(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    _reset_caches()
    try:
        assert isinstance(get_llm_matcher(), AnthropicLLMMatcher)
    finally:
        _reset_caches()
```

- [ ] **Step 2: Запустить — падает**

Run: `cd backend && uv run pytest tests/test_llm_matcher_factory.py -v`
Expected: FAIL (фабрика всегда строит Anthropic / ссылается на удалённый `settings.llm_model`).

- [ ] **Step 3: Переписать фабрику**

В `backend/app/api/deps.py` убедиться, что импортирован `OpenRouterLLMMatcher`
(`from app.infrastructure.ai.openrouter_matcher import OpenRouterLLMMatcher` рядом с импортом `AnthropicLLMMatcher`).
Заменить тело `get_llm_matcher()` на:

```python
@lru_cache
def get_llm_matcher() -> LLMMatcher:
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        return AnthropicLLMMatcher(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_llm_model,
            timeout_s=settings.ai_call_timeout_s,
            retry_budget=settings.transient_retry_budget,
        )
    if settings.llm_provider == "openrouter":
        return OpenRouterLLMMatcher(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=settings.openrouter_llm_model,
            timeout_s=settings.ai_call_timeout_s,
            retry_budget=settings.transient_retry_budget,
        )
    raise ValueError(f"Неизвестный LLM_PROVIDER: {settings.llm_provider!r}")  # страховка (конфиг уже валидирует)
```

- [ ] **Step 4: Обновить `.env.example`**

В `backend/.env.example` заменить строку `LLM_MODEL=claude-3-5-sonnet-20240620` на:

```
# LLM-арбитр матчинга: провайдер. openrouter (по умолчанию) | anthropic.
LLM_PROVIDER=openrouter
# Модель арбитра — отдельно на провайдера (слаги в разных неймспейсах!). Только обычные chat-модели
# (reasoning не поддерживается: малый max_tokens обрежет рассуждение). OpenRouter-матчер
# переиспользует OPENROUTER_API_KEY (тот же, что эмбеддер); Anthropic-арбитр — ANTHROPIC_API_KEY.
OPENROUTER_LLM_MODEL=anthropic/claude-3.5-sonnet
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
ANTHROPIC_LLM_MODEL=claude-3-5-sonnet-20240620
```

- [ ] **Step 5: Запустить — зелёный + полный прогон + ruff**

Run: `cd backend && uv run pytest tests/test_llm_matcher_factory.py -v && PYTHONIOENCODING=utf-8 uv run pytest && uv run ruff check .`
Expected: фабрика-тесты PASS; полный сьют зелёный (прежние матчинг-тесты на `FakeLLMMatcher` не задеты); ruff чисто.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/deps.py backend/.env.example backend/tests/test_llm_matcher_factory.py
git commit -m "feat(matching): get_llm_matcher ветвится по LLM_PROVIDER (OpenRouter дефолт) + .env.example"
```
