# Tree-matching ядро: PR 1 (структурный движок за флагом, без фонда)

**Дата:** 2026-08-28  
**Статус:** ✅ Завершено (backend: 519 passed / 3 skipped из 522 тестов, `pytest`; frontend: 310 passed, 37 тестовых файлов, `vitest`; ruff clean, frontend typecheck/lint/format clean)  
**Ветка:** `feat/tree-matching-core` (код заморожен на `d6fca58`; документация — отдельными коммитами поверх)  
**Спека:** [2026-08-27-tree-matching-core-design.md](../superpowers/specs/2026-08-27-tree-matching-core-design.md)

Вторая машина сопоставления — структурная: чанкирует смету по разделам и отправляет каждый чанк LLM со ВСЕМ справочником в промпте (кэшируется через prompt caching), вместо построчного RAG. Движок тщательно спроектирован как fail-closed и защищён от галлюцинаций; фонд решений отложен на PR 3.

---

## Что сделано

### 1. Домен (`app/domain/tree_matching.py`, `entities.py`, `decision_fund.py`)

Пять чистых функций без I/O и три расширения сущностей:

1. **`resolve_parents(nodes) → list[int | None]`** — индексы родителей по стеку глубин (переиспользует существующий `resolve_ancestor_indices`). Коды не смотрим; позиционный стек — один источник правды.

2. **`effective_ancestor_context(idx, nodes, parents) → AncestorContext`** — уникальная функция для всех слоёв (движка, фонда, промоушена). Подъём по цепочке предков: доверенные (reviewed/confident) vs недоверенные (needs_review) → как результат `AncestorContext(trusted_code, has_uncertain_barrier)`. Барьер = флаг ненадёжности контекста.

3. **`split_sections(nodes, parents, *, max_rows, budget_tokens, row_tokens) → list[Chunk]`** — рекурсивный чанкинг с жадной пакировкой потомков. Лимит: макс строк И макс токенов (`row_tokens` — функция стоимости одной строки, задаёт вызывающий). Чанки одного раздела упорядочены (родитель раньше детей). Один узел, который не влезает в бюджет сам по себе → цель `error` с `tree_row_too_large`.

4. **`validate_verdicts(raw, targets, catalog_codes, ctx_of) → dict[int, Validated]`** — валидирует пачку сырых вердиктов сразу для всех целей (используется тестами/будущим PR 2 харнессом, не сервисом — см. TECH_DEBT). Строится поверх `validate_one` — той же функции, что и `TreeMatchingRunner` вызывает per-target: типы, согласованность kind/code, существование кода в каталоге, позиция в дереве. Любой флаг валидации (unknown_code, inconsistent, malformed, outside_parent, missing) не роняет вызов — маппится в статус в `to_node_match`.

5. **`to_node_match(validated, ctx, catalog) → NodeMatch`** — **единственный** путь в `confident`: `article` + `sure` + без флагов + без uncertain_barrier. Остальные → needs_review (если эмодели, но данные сомнительны) или no_match/excluded/error.

Плюс три новые сущности:
- **`TreeNode`** — одна строка сметы с полями для движка (id, source_index, depth, code, name, status, review_status, matched_*, final_*).
- **`SectionMatchRequest`** — запрос к LLM: nodes (чанк), ancestors (путь), hints (крошки), targets (id, по которым нужен вердикт), catalog, precedents.
- **`NodeVerdict`** — ответ LLM per-узел: node_id, kind (article/org/none), article_code, sure, alt_code.

**Расширения:**
- **`MatchCandidate.score: float | None`** (было `float`) — `null` вместо `0`, чтобы не путать «отсутствие скора» с ошибочным скором.
- **`AncestorContext`** — новая dataclass для обоих движков.
- **`FUND_KEY_VERSION = 3`** и **`fund_key_v3(node, ctx) → str | None`** — ключ фонда версии 3: `normalize_cache_key(node.name) + "\x1f" + (ctx.trusted_code or "")` (`\x1f` — разделитель, не совпадающий с текстом; `None`, если контекст под барьером needs_review). Версия не влияет на PR 1 (фонд выключен), но живёт для PR 3.

### 2. Порты и репозитории (`domain/ports.py`, `infrastructure/db/`)

**Новый порт:**
- **`TreeMatcher(ABC).match_section(req: SectionMatchRequest) → SectionMatchResponse`** — единственный новый внешний сервис.

**Расширения `EstimateRepository`:**
- **`fetch_tree(estimate_id) → list[TreeNode]`** — все строки в порядке source_index.
- **`save_node_match_cas(node_id, result, expected_statuses) → bool`** — UPDATE с предикатом `status IN (:expected) AND review_status='unreviewed'`, возвращает `False` при проигранной гонке.
- **`refresh_tree_node(node_id) → TreeNode`** — перечитать один узел после проигранного CAS.

**Расширения `ArticleRepository`:**
- **`list_catalog() → list[CatalogArticle]`** — весь справочник (id, code, name, parent_code).

`DecisionFundRepository` в PR 1 не расширялся: фонд для tree-движка выключен (`fund_enabled=False`,
см. §4 ниже), выборка прецедентов по нормализованным именам (спека §11 п.3 называет её
`records_for_names`) — работа PR 3, в коде её пока нет.

### 3. Инфраструктура (`infrastructure/ai/`)

**`tree_prompt.py`:**
- Ассемблировка запроса: каталог (идентичный для всех чанков, кэшируется), раздел чанка с подсказками (доверенные крошки и фонд-прецеденты), целевые узлы для вердикта.
- **Прямая JSON-парсинг** через `JSONDecoder.raw_decode` — обработка усечённых ответов (finish_reason=length).
- **Fallback на `None`** для малформированного JSON вместо ошибки.

**`OpenRouterTreeMatcher` (`infrastructure/ai/openrouter_tree_matcher.py`):**
- Реализация порта. Вызывает OpenRouter через `httpx` (модель конфигурируется через `config.openrouter_tree_model`).
- Параметры: `max_tokens`, `reasoning_effort` (из конфига `tree_reasoning_effort`), `cache_control: ephemeral` на каталоге.
- Парсинг ответа: вектор вердиктов из JSON (fail-closed) + повторные попытки на сбой сети.
- Инструментируется через существующий `instrumented_call` (provider, model, latency, outcome).

### 4. Сервис (`services/tree_matching_service.py`)

**`TreeMatchingRunner`** — оркестратор для одной сметы:

```
lock → running → fetch_tree + resolve_parents
                 split_sections (чанкинг)
                 по каждому чанку (process(), сверху вниз):
                   build_request (ancestors, hints, targets, catalog)
                   tree_matcher.match_section
                   на каждую цель: validate_one + to_node_match
                   save_node_match_cas
                     проигран CAS → refresh_tree_node (не перезаписывать вердикт,
                                     подтянуть актуальное состояние для контекста детей)
                 в finally: release lock → ready / partial_error
```

Решения (видны в коде):
1. **Бюджет из данных, не из промпта:** на сервис-уровне считаем `estimate_tokens` по каталогу, по имени раздела, по имёнам узлов. Сервис НЕ импортирует `infrastructure/` и никогда не рендерит промпт.
2. **Дедуп и линейный проход:** чанки обработаны сверху вниз (родитель раньше дочерних), узлы-цели дедуплят по вердиктам (дублики → первый берётся, остальные — warning).
3. **Fail-closed:** любая внутренняя ошибка движка (JSON, типы вердиктов, unknown_code) → запись `error` с match_error `tree_*`, никогда молчаливо не `confident`.

**Выбор движка живёт в composition root, не в сервисе:** `build_estimate_matching_service`
(`app/api/deps.py:222`) читает `settings.matching_engine`; при `"tree"` собирает
`TreeMatchingRunner(..., fund_enabled=False)` и передаёт его в `EstimateMatchingService(..., tree=runner)`.
`fund_enabled` — kwarg конструктора `TreeMatchingRunner`, а не поле запроса; `True` роняет
`NotImplementedError` прямо в `__init__` (фонд ждёт PR 3).

Сам `EstimateMatchingService.match_estimate` не знает про `matching_engine` — он проверяет
`if self._tree is not None:` (`app/services/estimate_matching_service.py:89`) и либо целиком идёт по
tree-ветке (`self._tree.run(estimate_id)`), либо по старому RAG-пути (classify → fund → embed → gate →
match). `self._tree` — `TreeMatchingRunner | None`, `None` по умолчанию (RAG).

### 5. Конфиг (`app/core/config.py`)

8 новых settings (обычные поля `str`/`int`, без `Literal` — проверяются вручную в
`@model_validator _validate_llm`, кроме одного пропуска, см. TECH_DEBT):

- **`matching_engine: str`** = `"rag"` — выбор движка; валидатор ограничивает `{"rag", "tree"}`.
- **`openrouter_tree_model: str`** = `"anthropic/claude-sonnet-5"` — слаг OpenRouter для tree-движка;
  валидатор требует непустую строку.
- **`tree_reasoning_effort: str`** = `"low"` — `reasoning.effort` в запросе к OpenRouter; **не
  валидируется** (см. TECH_DEBT «`tree_reasoning_effort` не валидируется»).
- **`tree_context_window: int`** = `200_000` — окно модели, задаётся явно (не читается из каталога
  моделей); валидатор требует `> 0`.
- **`tree_chunk_rows: int`** = `120` — целевой размер чанка в строках; валидатор требует `> 0`.
- **`tree_min_chunk_rows: int`** = `10` — нижняя граница при обрезке чанка на truncated-ответе;
  валидатор требует `1 ≤ tree_min_chunk_rows ≤ tree_chunk_rows`.
- **`tree_output_reserve_per_row: int`** = `48` — токенов на ответ, закладываемых на КАЖДУЮ
  потенциальную цель чанка (и в бюджет чанка, и в `max_tokens` запроса); валидатор требует `> 0`.
- **`tree_precedents_budget: int`** = `2_000` — резерв токенов под блок ПРЕЦЕДЕНТЫ (не используется
  в PR 1 — фонд выключен); валидатор требует `>= 0`.

Две доли бюджета чанка — НЕ settings, а модульные константы в `app/services/tree_matching_service.py`
(не настраиваются через `.env`, зашиты в коде):
- **`_CATALOG_SHARE = 0.25`** — справочник не должен занимать больше 25% окна модели
  (иначе `CatalogTooLargeError`).
- **`_CONTEXT_SHARE = 0.80`** — под сам чанк (система + каталог + предки + строки + резерв ответа +
  margin) отводится не больше 80% окна.

### 6. Фронтенд

- **`MatchCandidate.score`** теперь `number | null` во всех типах (`lib/types.ts`).
- **Рендеринг:** строка или кандидат БЕЗ скора (`score === null`) → элемент со скором не рендерится вообще (`ReviewCard.tsx`, `ReviewGrid.tsx` — условие `score !== null`); раньше при отсутствии скора туда подставлялся `0` и рендерился как `0.00` тем же `<span className="font-mono text-xs text-muted-foreground">` (скор нигде не был цветным бейджем — это всегда был обычный текстовый спан).
- Логика ревью не изменилась; кандидаты из обоих движков одинаковы.

### 7. Тесты (11 задач, каждая с набором тестов)

✅ Backend: 519 passed / 3 skipped из 522 тестов (`pytest`). Frontend: 310 passed, 37 тестовых файлов
(`vitest`) — отдельный сьют, не входит в число выше.

Ключевые сценарии (реальные имена тестов, без выдуманных wildcard-групп):
- `test_tree_repository_integration.py` — `test_fetch_tree_orders_by_source_index`,
  `test_save_node_match_cas_and_refresh_after_review`,
  `test_list_catalog_resolves_parent_code_via_parent_id`.
- `test_tree_matching_domain.py`, префикс `test_split_*` — чанкинг (greedy packing, oversized узлы,
  recursion, обрезка по токен-бюджету).
- `test_tree_matching_domain.py`, префикс `test_context_*` — цепочка доверия `effective_ancestor_context`
  с барьерами.
- `test_resolve_parents_positional_not_by_code` — индексы родителей по стеку глубин, не по коду.
- `test_validate_flags`, `test_validate_many_ignores_foreign_and_duplicates` — валидационные пути
  `validate_one`/`validate_verdicts`, fail-closed.
- `test_to_node_match_matrix` — маппинг в статусы (только один путь в `confident`).
- `test_tree_matching_service.py` — сценарии `TreeMatchingRunner.run` без общего префикса, напр.
  `test_happy_path_writes_statuses_and_uses_parent_context_within_chunk`,
  `test_lost_cas_refreshes_parent_before_children`,
  `test_truncated_response_splits_chunk_then_errors_below_min`.
- `test_openrouter_tree_matcher.py` — адаптер, напр.
  `test_sends_cached_system_block_reasoning_and_max_tokens`, `test_truncated_response_flagged`,
  `test_transport_error_exhausts_to_transient`.

---

## Ключевые решения

1. **Бюджет из данных.** `TreeMatchingRunner` считает `estimate_tokens` по строкам, НЕ рендерит промпт. Сервис полностью отделён от инфраструктуры; это требование Clean Architecture.

2. **`SectionMatchResponse` сырые словари.** LLM-адаптер возвращает список словарей-вердиктов из JSON. Валидация и маппинг — в доменном слое (`validate_one` per-target внутри `TreeMatchingRunner`, `to_node_match`), никогда в адаптере → fail-closed.

3. **Единственный путь в `confident`.** Вердикт должен быть type `article`, `sure=true`, НОЛЬ флагов валидации, и **не было uncertain_barrier** в цепочке предков. Остальные комбинации → needs_review/no_match/error. Стратегия: высокая полоса пропускания (LLM выбирает), но узкие ворота уверенности.

4. **Фонд выключен в PR 1.** `fund_enabled=True` → `NotImplementedError`. Фонд ждёт версии 3 (спека §6, PR 3). Константа `FUND_KEY_VERSION = 3` и функция `fund_key_v3` уже готовы.

5. **RAG-путь неизменен.** Движок выбирается флагом `matching_engine`; если `"rag"`, код идёт по старому каналу. При дефолте `"rag"` и без явного переключения в конфиге пользователь видит RAG (как сейчас).

---

## Что осталось

Спека делит работу на 4 PR (§11 плана); эта PR закрывает п.1, ниже — пп.2–4:

### PR 2 — Харнесс калибровки
- `--engine rag|tree|both` флаг CLI
- Замер `top_1_strict` и других метрик на бенчмарке
- Frozen RAG baseline (воспроизводимость спайка)
- Калибровка `tree_reasoning_effort`, `tree_max_chunk_rows`
- В финале — decision о дефолте и скорости перехода

### PR 3 — Фонд решений v3
- `fund_enabled=True` (теперь выбросит, будет работать)
- Интеграция `fund_key_v3` в чанк-обработку
- Прецедент-записи в промпт
- Фронт: подсказка соседа (`dependents_hint`), если фонд подтвердил сестру

### PR 4 — Гейт качества
- Спека §9: порог top-1 в проде (если дойдёт)
- Flipping default `matching_engine = "tree"`
- Удаление RAG-кода (не нужен больше)
- Финализация

---

## Файлы

Список получен из `git diff --name-only 0ca2882..a6bb8ad` (весь код PR 1, без документации).

**Backend:**
- `app/api/deps.py` — **реальная точка выбора движка**: `build_estimate_matching_service` читает
  `settings.matching_engine`, при `"tree"` собирает `TreeMatchingRunner` через новый `get_tree_matcher()`
  и передаёт его в `EstimateMatchingService(tree=...)`.
- `app/api/schemas.py` — `MatchCandidateOut.score: float | None` (было `float`, спека §7.1).
- `app/core/config.py` — 8 новых settings движка tree (см. раздел «Конфиг» выше).
- `app/domain/decision_fund.py` — `FUND_KEY_VERSION = 3`, `fund_key_v3()` (готово для PR 3, в PR 1 не
  вызывается).
- `app/domain/entities.py` — новые сущности: `TreeNode`, `CatalogArticle`, `FundPrecedent`,
  `SectionMatchRequest`, `SectionMatchResponse`, `NodeVerdict`, `AncestorContext`;
  `MatchCandidate.score: float | None` (было `float`).
- `app/domain/ports.py` — новый порт `TreeMatcher.match_section(req) → SectionMatchResponse`;
  расширения `EstimateRepository` (`fetch_tree`, `refresh_tree_node`, `save_node_match_cas`) и
  `ArticleRepository.list_catalog()`.
- `app/domain/tree_matching.py` (новый, 327 строк) — чистые функции ядра: `resolve_parents`,
  `effective_ancestor_context`, `split_sections`, `hint_for`/`build_hints`, `validate_one`/
  `validate_verdicts`, `to_node_match`, `neighbors`.
- `app/infrastructure/ai/openrouter_tree_matcher.py` (новый) — `OpenRouterTreeMatcher`, реализация
  порта `TreeMatcher` через OpenRouter `chat/completions`.
- `app/infrastructure/ai/tree_prompt.py` (новый) — сборка промпта (`SYSTEM_PROMPT`, `render_catalog`,
  `render_ancestors`, `render_fragment`, `build_user_prompt`) и разбор ответа (`parse_verdicts`,
  через `json.JSONDecoder.raw_decode`).
- `app/infrastructure/db/article_repository.py` — реализация `list_catalog()`.
- `app/infrastructure/db/estimate_repository.py` — реализация `fetch_tree`, `save_node_match_cas`,
  `refresh_tree_node`.
- `app/services/estimate_matching_service.py` — конструктор принимает `tree: TreeMatchingRunner | None`;
  `match_estimate` ветвится по `if self._tree is not None`.
- `app/services/tree_matching_service.py` (новый, 222 строки) — `TreeMatchingRunner`: `run()` —
  единственная публичная точка входа, вложенное замыкание `process()` на чанк.

**Frontend:**
- `src/lib/types.ts` — `MatchCandidate.score: number | null` (было `number`, дефолт `?? 0` убран).
- `src/lib/api/estimates.ts` — `RowDto` и `rowFromDto` пробрасывают `score` как `null`, не подставляют `0`.
- `src/lib/mock/api.ts` — CSV-экспорт (`exportEstimateCsv`) обрабатывает `score === null` отдельной веткой.
- `src/pages/estimate/ReviewCard.tsx` — рендер скора кандидата/AI-рекомендации только при `score !== null`.
- `src/pages/estimate/ReviewCard.test.tsx` — тесты на условный рендеринг при `score: null`.
- `src/pages/estimate/ReviewGrid.tsx` — колонка скора в гриде: то же условие `r.score !== null`.

**Tests (backend, новые/расширенные файлы):**
- `backend/tests/test_tree_matching_domain.py` (новый) — доменные функции `tree_matching.py`.
- `backend/tests/test_tree_matching_service.py` (новый) — сценарии `TreeMatchingRunner`.
- `backend/tests/test_tree_prompt.py` (новый) — сборка промпта и `parse_verdicts`.
- `backend/tests/test_openrouter_tree_matcher.py` (новый) — адаптер (кэш-блок, reasoning, retry, truncate).
- `backend/tests/test_tree_repository_integration.py` (новый) — `fetch_tree`/CAS/`list_catalog` на реальной БД.
- `backend/tests/test_deps_tree.py` (новый) — DI: `build_estimate_matching_service` собирает
  `tree=` только при `matching_engine == "tree"`.
- `backend/tests/test_config.py` — `+34` строк: дефолт/валидация `matching_engine`.
- `backend/tests/test_estimate_matching_service.py` — `+52` строки: tree-ветка обходит
  classify/embedder/gate; пустой каталог блокирует смету без исключения наружу.
- `backend/tests/test_estimate_repo_cas.py` (новый) — CAS-предикаты `save_node_match`/
  `save_node_match_cas`, `fetch_tree`+`refresh`.
- `backend/tests/test_estimate_row_payload.py` — `+14` строк: `score: None` сериализуется в `null`.
- `backend/tests/fakes.py` — `+92` строки: фейки под tree-порты (`ArticleRepository.list_catalog`,
  `EstimateRepository.fetch_tree`/`save_node_match_cas`/`refresh_tree_node`, фейковый `TreeMatcher`).

`.env.example` в PR 1 не менялся — все 8 `tree_*`/`matching_engine` settings имеют дефолты в
`config.py` и не требуют записи в `.env`, пока не нужно переопределить значение.

---

## Как включить локально

1. В `backend/.env` добавить (или отредактировать, если строка уже есть) `MATCHING_ENGINE=tree`.
   Без этой строки дефолт — `rag` (`config.py`).
2. Запустить бэк: `just dev-back`.
3. В отдельном окне — Celery-воркер (нужен для асинхронного матчинга):
   `cd backend; uv run celery -A app.infrastructure.tasks.celery_app worker --pool=solo -l info`.
4. Загрузить смету через фронтенд — она уйдёт в tree-движок.

Чтобы вернуться на RAG — отредактировать ту же строку `MATCHING_ENGINE=` в `.env` на `rag`
(или удалить её целиком — дефолт и так `rag`) и перезапустить бэк. Две строки `MATCHING_ENGINE=`
в одном `.env` не должно быть — `pydantic-settings` берёт значение из файла один раз, поведение
при дубле не документировано.

---

## Поведение при ошибках

1. **Недоступен OpenRouter / timeout (`TransientError`):** `instrumented_call` повторит до лимита
   ретраев, потом чанк целиком → `error` (`match_error` вида `tree_transient: <текст исключения>`);
   этот чанк помечается как `failed_roots`, и все чанки-потомки его корня тоже уходят в `error`
   (`tree_ancestor_failed`), не дожидаясь собственного вызова LLM.
2. **Модель вернула нечитаемый JSON:** `parse_verdicts` не находит валидный JSON-массив → `None` →
   адаптер отдаёт `SectionMatchResponse(items=[], truncated=False)`. Для каждой цели чанка вердикта
   в ответе нет → `validate_one` получает `None` → флаг `missing` → `to_node_match` пишет `error`
   с `match_error=tree_missing_verdict`.
3. **Узел больше бюджета сам по себе:** `split_sections` помечает его `oversized`, `TreeMatchingRunner`
   пишет `error` (`match_error=tree_row_too_large`) без вызова LLM и продолжает остальное.
4. **Оператор успел отревьюить строку, пока движок её обрабатывал (CAS-проигрыш):**
   `save_node_match_cas` вернёт `False` — движок НЕ перезаписывает решение оператора; `refresh_tree_node`
   лишь подтягивает актуальное состояние узла в рабочее дерево (чтобы дети видели верный контекст
   предка при вычислении `effective_ancestor_context`). Вердикт для самой этой строки не переписывается
   и не повторяется — CAS для того и нужен, чтобы уважать ручное решение.

Все пути → статусы `error`/`needs_review`/`no_match`, никогда молча `confident`.

---

## Релевантные документы

- **Спека:** [2026-08-27-tree-matching-core-design.md](../superpowers/specs/2026-08-27-tree-matching-core-design.md) (полный дизайн, все решения, измеры)
- **План:** [plan](../superpowers/plans/2026-08-28-tree-matching-pr1.md) (задачи 1–11 закрыты, task 12 — эта документация)
- **PIPELINE:** [../PIPELINE.md](../PIPELINE.md) — добавлен раздел про tree-движок (рядом с RAG §6)
- **TECH_DEBT:** [../TECH_DEBT.md](../TECH_DEBT.md) — 10 новых записей из ревью (разлёт чанков, `_CODE_ORDER`, `_coerce`, логирование, очистка тестов, валидация `tree_reasoning_effort`, unused `validate_verdicts`, `articles.ts` score=0, параллелизм разделов, provenance контекста)

---

## Выводы

PR 1 реализовала полностью независимый движок: новая архитектура (отделена от RAG, отделена от фонда), полное покрытие тестами, fail-closed валидация, готовность к калибровке (PR 2). Переключение на флаг; дефолт остаётся RAG. Оттуда видно, что движок даёт выигрыш по качеству (спайк: 94.9% vs 77% RAG), но требует калибровки по speed и cost перед prod-флипом (PR 4).
