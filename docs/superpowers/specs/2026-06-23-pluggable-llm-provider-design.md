# Спецификация: переключаемый LLM-провайдер арбитра матчинга

**Дата:** 2026-06-23
**Статус:** дизайн утверждён, готов к плану реализации

## Место в общей картине

Отдельное улучшение поверх SP2 (асинхронный матчинг). **Не часть SP3** (ревью/правки + запись
`Статья СМР` + выгрузка) — SP3 не трогаем. Меняется только адаптерный слой LLM-арбитра; порт
`LLMMatcher` и логика `MatchingService.match_one` (порог → арбитр → честный score) остаются как есть.

## Задача

Сейчас LLM-арбитр (выбор статьи из топ-K при `score ≤ 0.90`) жёстко завязан на прямой Anthropic
SDK (`AnthropicLLMMatcher`, ключ `ANTHROPIC_API_KEY`). Нужно сделать провайдера **переключаемым по
конфигу**: OpenRouter (новый, дефолт) или Anthropic (текущий, опция). Архитектура должна позволять
добавить Google как +1 адаптер без изменения порта/сервисов. Эмбеддинг (`OpenRouterEmbedder`) —
**вне объёма**, остаётся как есть.

## Вне объёма

- Эмбеддер (узлов/справочника) — остаётся OpenRouter, не делаем переключаемым.
- Google (Gemini) адаптер — не сейчас; абстракция оставляет его добавлением одного файла.
- Любые правки SP3.

## Архитектура (подход A)

Порт `LLMMatcher.choose_best(query, candidates) -> TemplateArticle | None` — **без изменений**.

**Общий модуль** `backend/app/infrastructure/ai/llm_matching_common.py` — единая семантика арбитража,
независимая от провайдера (от неё зависят «честный score» и трактовка отказа, поэтому она ОДНА):
- `SYSTEM_PROMPT` — константа (усилить требование «верни ТОЛЬКО число, без слов»).
- `build_user_prompt(query, candidates) -> str` — нумерованный список кандидатов (`1. [code] name`).
- `parse_choice(text, candidates) -> TemplateArticle | None` — извлекает **первый целочисленный токен**
  (`re.search(r"\d+")`, не равенство — устойчиво к «option 2»/markdown); `0`/нет числа/вне диапазона
  `1..K` → `None` (отказ). Возвращает `candidates[choice-1].article`.

**Адаптеры** (оба тонкие: только вызов провайдера + классификация транзиента; промпт/парсинг — из common):
- `AnthropicLLMMatcher` (рефактор) — прямой `anthropic` SDK; переводим на `llm_matching_common`,
  добавляем `temperature=0` (сейчас не задан → дефолт 1.0, недетерминированно).
- `OpenRouterLLMMatcher` (новый) — OpenAI-совместимый `POST {openrouter_base_url}/chat/completions`
  через `httpx` (зеркалит `OpenRouterEmbedder`: инъекция `client` для тестов, `retry_transient` +
  `_is_transient`). `temperature=0`, `max_tokens` малый (≈16). Заголовки атрибуции OpenRouter
  `HTTP-Referer` и `X-Title`. Переиспользует `OPENROUTER_API_KEY` (новый ключ не нужен).

**Фабрика** `get_llm_matcher()` в `deps.py` — fail-fast на старте:
- читает `settings.llm_provider` → строит нужный адаптер;
- **неизвестный провайдер** → `ValueError` с понятным сообщением;
- **отсутствует ключ выбранного провайдера** (`OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY`) → `ValueError`
  на старте (а не на первом запросе).

## Конфиг (`backend/app/core/config.py`)

- `llm_provider: str = "openrouter"` — `"openrouter"` | `"anthropic"`.
- **Per-provider модели** (переключение = флип одной `LLM_PROVIDER`; слаги в разных неймспейсах):
  - `openrouter_llm_model: str = "anthropic/claude-3.5-sonnet"` — слаг OpenRouter (⚠ сверить актуальный
    перед мерджем, слаги меняются).
  - `anthropic_llm_model: str = "claude-3-5-sonnet-20240620"` — нативный Anthropic id.
- `openrouter_base_url: str = "https://openrouter.ai/api/v1"` — только для OpenRouter-матчера
  (имя по провайдеру, как существующий `embedding_base_url`; SDK-адаптер Anthropic его игнорирует).
- **Депрекация `llm_model`:** поле удаляем. Чтобы не было тихого игнора (`extra="ignore"` молча
  проглотит старую `LLM_MODEL`), добавляем `@model_validator`, который **роняет старт** с понятным
  сообщением, если в окружении задан `LLM_MODEL`: «`LLM_MODEL` устарел → задайте `OPENROUTER_LLM_MODEL`
  и/или `ANTHROPIC_LLM_MODEL`». (Fallback-чтение отвергнуто: старый Anthropic-слаг, поданный в
  OpenRouter, — некорректен → это и есть тот самый misroute, который фича призвана исключить.)
- `GOOGLE_API_KEY` — оставляем зарезервированным под будущий Google-адаптер (не «мёртвый», а «впрок»).

## Поведение и крайние случаи

- **Разговорчивость моделей (главная угроза «одной семантике»):** через OpenRouter роутимся на разные
  модели с разной дисциплиной вывода. Защита: (1) `parse_choice` извлекает первый int, не требует
  равенства; (2) `temperature=0` на обоих адаптерах; (3) системный промпт жёстко требует «только число»;
  (4) малый `max_tokens` (≈16) подрезает болтливость. Остаточный риск (напр. «между 1 и 3 выбираю 2» →
  первый int = 1) считаем приемлемым при temp=0 + строгом промпте + max_tokens; не усложняем.
- **Отказ:** `0` / не-число / вне диапазона → `None` → `match_one` трактует как `no_match` со снимком.
- **Галлюцинация** (модель назвала статью вне топ-K): индекс вне `1..K` → `None`; плюс существующая
  валидация в `match_one` (выбранный обязан быть из кандидатов) остаётся второй линией.
- **OpenRouter 200 с upstream-ошибкой в теле:** не ловится по status code. OpenRouter-адаптер
  инспектирует JSON: если нет валидного `choices[0].message.content` ИЛИ присутствует объект `error`
  → поднимаем `TransientError` (ретрай по бюджету; при исчерпании — узел `error` → `partial_error`),
  а НЕ возвращаем `None` (иначе ложный `no_match`).

## Транзиентность

Два независимых `_is_transient` (Anthropic — типизированные исключения SDK; OpenRouter — httpx +
status code) допустимы, но должны покрывать **одни и те же логические условия**: сеть/таймаут, 429,
5xx. Дополнительно у OpenRouter — ветка «200 с error-телом» (выше).

## Тестирование (фейки, без сети)

- `parse_choice` (common): `"2"`→кандидат 2; `"0"`/мусор/вне диапазона→`None`; **обёрнутый ответ**
  («The best match is option 2.» / markdown) → кандидат 2 (защита от разговорчивости).
- `OpenRouterLLMMatcher` с инъецированным фейковым `httpx`-клиентом: успешный `"2"`→кандидат;
  transport/timeout→ретраи→`TransientError`; **200 с `error` в теле / без `choices`→`TransientError`**;
  отправляются заголовки атрибуции.
- `AnthropicLLMMatcher` (после рефактора) — поведение не изменилось (тот же парсинг через common).
- Фабрика `get_llm_matcher()`: правильный тип на каждый `llm_provider`; неизвестный→`ValueError`;
  **отсутствует ключ выбранного провайдера→`ValueError` на старте**.

## Миграция / выкатка

- `.env.example`: заменить `LLM_MODEL` на `LLM_PROVIDER` + `OPENROUTER_LLM_MODEL` + `ANTHROPIC_LLM_MODEL`
  + `OPENROUTER_BASE_URL`; пояснить, что OpenRouter-матчер переиспользует `OPENROUTER_API_KEY`.
- Перед мерджем — **сверить актуальный слаг** `anthropic/claude-3.5-sonnet` на стороне OpenRouter.
- `backend/.env` (боевой) — задаёт человек; секреты не коммитим.

## Журнал решений (кратко)

1. Подход **A** (адаптеры за портом + общий `llm_matching_common`) — гарантирует идентичную семантику.
2. Провайдеры сейчас: **OpenRouter + Anthropic**; Google — позже одним адаптером.
3. Дефолт — **OpenRouter** (переиспользует `OPENROUTER_API_KEY` эмбеддера).
4. Модели — **per-provider** переменные (слаги в разных неймспейсах; один общий `LLM_MODEL` ломает
   переключение).
5. Старый `LLM_MODEL` — **fail-fast на старте** (не тихий игнор, не fallback-misroute).
6. Fail-fast в фабрике — **и неизвестный провайдер, и отсутствующий ключ**.
7. `temperature=0` на обоих адаптерах; `parse_choice` — первый int; OpenRouter 200-с-error-телом →
   `TransientError`; заголовки атрибуции OpenRouter.
