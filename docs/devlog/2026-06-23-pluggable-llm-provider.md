# 2026-06-23 — Переключаемый LLM-провайдер арбитра матчинга

## Что сделано

Самостоятельное улучшение поверх SP2: LLM-арбитр матчинга (выбор статьи из топ-K, когда
`score ≤ 0.90`) стал **переключаемым по конфигу** — провайдер `openrouter` (дефолт) или
`anthropic`. Семантика промпта и парсинга ответа теперь живёт в **одном** общем модуле
`llm_matching_common` и идентична у обоих провайдеров — от неё зависят «честный score» и
трактовка отказа, поэтому она ОДНА. Тонкие адаптеры отвечают только за сетевой вызов и
классификацию ошибок. Конфиг валидируется **fail-fast** при инстанцировании `Settings`
(провайдер/ключ/депрекация `LLM_MODEL`).

Спек: [docs/superpowers/specs/2026-06-23-pluggable-llm-provider-design.md](../superpowers/specs/2026-06-23-pluggable-llm-provider-design.md).
План: [docs/superpowers/plans/2026-06-23-pluggable-llm-provider.md](../superpowers/plans/2026-06-23-pluggable-llm-provider.md).
PR: [#8](https://github.com/zhukovvlad/ciw-tenders/pull/8) (база `main`). Коммиты `4e7e4ba..8069cf0` (5 задач + 2 правки модели).

## Архитектура

`api → services → domain ← infrastructure`. Порт `LLMMatcher.choose_best(query, candidates)`
**не менялся**. Общий модуль `infrastructure/ai/llm_matching_common.py` несёт `SYSTEM_PROMPT`,
`build_user_prompt`, `parse_choice`. Адаптеры (`AnthropicLLMMatcher`, `OpenRouterLLMMatcher`)
переиспользуют его и инжектят клиента (тесты без сети). Фабрика `get_llm_matcher()` в
композит-руте (`api/deps.py`) ветвится по `settings.llm_provider`; валидация — в
`@model_validator(mode="after")` конфига (срабатывает на старте и FastAPI, и Celery).

## Бэкенд (5 задач)

- **Общий модуль (Task 1):** `build_user_prompt` листит кандидатов БЕЗ кода статьи (код в
  листинге провоцирует echo кода вместо номера строки → misroute). `parse_choice` берёт первый
  целочисленный токен (`re.search`, устойчиво к «option 2»/markdown); `0`/нет числа/вне диапазона
  `1..K` → `None` (отказ). `0` отсекается **до** индексации (off-by-one guard — иначе
  `candidates[-1]` ложный матч). Warning только на непустой-не-«0»-непарсящийся ответ.
- **Рефактор Anthropic (Task 2):** перевод на common, `temperature=0` (детерминизм), keyword-only
  `client` для инъекции фейка. Старые локальный `_SYSTEM_PROMPT` и инлайн-`re.search` удалены.
- **Новый OpenRouter (Task 3):** OpenAI-совместимый `POST /chat/completions` через `httpx`,
  атрибуция-хедеры `HTTP-Referer`/`X-Title`, `temperature=0`, малый `max_tokens`. Ключевое —
  обработка ошибки в теле ответа при HTTP 200: транзиент (`code==429`/`>=500`/пустые `choices`) →
  `_BodyError(transient=True)` → `TransientError` (ретрай); перманент (невалидный слаг/auth/кривая
  структура `choices`) → громкий `_BodyError(transient=False)`, всплывает до `partial_error` —
  **не** `None` (иначе тихий misroute). Граница транзиент/перманент запинена РАЗНЫМИ типами
  исключений, а не «оба просто исключение».
- **Конфиг (Task 4):** `llm_provider` + per-provider модели (`openrouter_llm_model`,
  `anthropic_llm_model`) + `openrouter_base_url`; `llm_model` помечен DEPRECATED. Единый
  `@model_validator`: депрекация (`llm_model is not None` → ошибка) → неизвестный провайдер →
  отсутствующий ключ выбранного провайдера (пустая строка = отсутствие).
- **Фабрика + `.env.example` (Task 5):** `get_llm_matcher()` ветвится по провайдеру (полная
  проводка `timeout_s`/`retry_budget` + `ValueError`-страховка), `@lru_cache` сохранён.
  `.env.example`: `LLM_MODEL` → `LLM_PROVIDER` + per-provider модели + предупреждение про
  reasoning-модели (малый `max_tokens` обрежет рассуждение — только обычные chat-модели).

## Контракт `retry_transient` (подтверждён, `retry.py` не менялся)

Неклассифицированное исключение (`classify→False`) пробрасывается как **оригинал, немедленно**
(перманентный `_BodyError` всплывает как `_BodyError`). Исчерпан бюджет на классифицированном
(`classify→True`) → `TransientError`. `budget=1` = один вызов, ноль ретраев. Эта граница и
разнотипность исключений — то, на чём держатся тесты OpenRouter-адаптера.

## Модели (после задач, по запросу — обе на Sonnet 4.6)

- OpenRouter: `OPENROUTER_LLM_MODEL=anthropic/claude-sonnet-4.6` (слаг сверен в живом каталоге).
- Anthropic: `ANTHROPIC_LLM_MODEL=claude-sonnet-4-6` — нативный id, **без датного суффикса**
  (сверено по справочнику Anthropic API). Sonnet 4.6 сохраняет параметр `temperature`, поэтому
  `temperature=0` в адаптере валиден; chat-модель, префилл не используется.

> Спека и план (замороженные на момент дизайна) фиксируют исходный слаг `anthropic/claude-3.5-sonnet`
> / `claude-3-5-sonnet-20240620` — он там был помечен «сверить перед мерджем». Боевой конфиг шипнут на
> 4.6 (этот девлог — источник правды о том, что реально задеплоено). Расхождение намеренное, доки не
> переписываются задним числом.

## Верификация (выполнена)

- Бэк: `PYTHONIOENCODING=utf-8 uv run pytest` → **166 passed, 1 skipped** (lock-integration gated);
  `uv run ruff check .` чисто. Прогон повторён после обеих правок модели.
- Тесты не ходят в сеть/БД/AI — инъекция фейкового `httpx.Client` (OpenRouter) / фейкового
  anthropic-клиента; конфиг через `monkeypatch`. `conftest` кладёт `OPENROUTER_API_KEY`/
  `ANTHROPIC_API_KEY`/`DATABASE_URL` в `os.environ` (на этом держатся happy-path конфига и фабрики).
- Дефолт провайдера — `openrouter` (переиспользует `OPENROUTER_API_KEY` эмбеддера, новый ключ не нужен).

## Решения и нюансы

- **Семантика — в одном месте.** Дублирование промпта/парсинга по адаптерам трактовалось бы как
  дефект ревью; `llm_matching_common` именно его устраняет.
- **Операционная мина `LLM_MODEL`.** Валидатор читает `os.environ` через поле — источник ему
  безразличен (env/`.env`/шелл-профиль/compose/k8s). Если `LLM_MODEL` задана где угодно, `conftest`
  инстанцирует `Settings` для каждого теста → падает **весь** pytest, при чистом гите. По ходу
  найдена и снята строка `LLM_MODEL=...` в `backend/.env` (gitignored).
- **Процесс:** subagent-driven (свежий субагент на задачу, независимое ревью spec+quality после
  каждой, фиксы по результатам) → финальное whole-branch ревью (opus): Ready to merge = Yes, без
  Critical/Important; сквозной путь перманентной ошибки → `partial_error` верифицирован против
  `estimate_matching_service.py`. Все накопленные замечания — deferrable (тест-гигиена).

## Долг / на будущее (вынесено в [TECH_DEBT](../TECH_DEBT.md))

- Полировочные Minor из ревью (тест-гигиена): слабый ассерт `"0" in SYSTEM_PROMPT`, позиционная
  сигнатура `_FakeClient.post`, `-> Never` на `_raise_body_error` → 🟢 в TECH_DEBT.
- Google-адаптер сознательно не делался (вне объёма) → раздел «Сознательно вне объёма» в TECH_DEBT.

## Дальше

Не зависит от SP3 (ревью/правки + запись «Статья СМР» + выгрузка) — то отдельный под-проект.
