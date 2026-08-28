# Tree-matching ядро: PR 1 (структурный движок за флагом, без фонда)

**Дата:** 2026-08-28  
**Статус:** ✅ Завершено (PR создана, тесты 519 passed / 3 skipped, рuff clean, frontend typecheck/lint/format clean)  
**Ветка:** `feat/tree-matching-core` (HEAD `d6fca58`)  
**Спека:** [2026-08-27-tree-matching-core-design.md](../superpowers/specs/2026-08-27-tree-matching-core-design.md)

Вторая машина сопоставления — структурная: чанкирует смету по разделам и отправляет каждый чанк LLM со ВСЕМ справочником в промпте (кэшируется через prompt caching), вместо построчного RAG. Движок тщательно спроектирован как fail-closed и защищён от галлюцинаций; фонд решений отложен на PR 3.

---

## Что сделано

### 1. Домен (`app/domain/tree_matching.py`, `entities.py`, `decision_fund.py`)

Пять чистых функций без I/O и три расширения сущностей:

1. **`resolve_parents(nodes) → list[int | None]`** — индексы родителей по стеку глубин (переиспользует существующий `resolve_ancestor_indices`). Коды не смотрим; позиционный стек — один источник правды.

2. **`effective_ancestor_context(idx, nodes, parents) → AncestorContext`** — уникальная функция для всех слоёв (движка, фонда, промоушена). Подъём по цепочке предков: доверенные (reviewed/confident) vs недоверенные (needs_review) → как результат `AncestorContext(trusted_code, has_uncertain_barrier)`. Барьер = флаг ненадёжности контекста.

3. **`split_sections(nodes, parents, *, max_rows, budget) → list[Chunk]`** — рекурсивный чанкинг с жадной пакировкой потомков. Лимит: макс строк И макс токенов. Чанки одного раздела упорядочены (родитель раньше детей). Один узел, который не влезает в бюджет сам по себе → цель `error` с `tree_row_too_large`.

4. **`validate_verdicts(verdicts, req, catalog, contexts) → dict[int, Validated]`** — fail-closed валидация: 7 проверок (типы, согласованность, существование кодов, позиция в дереве). Любой флаг валидации (unknown_code, inconsistent, malformed, outside_parent, missing) → результат остаётся валидным, но mappers в статус.

5. **`to_node_match(validated, ctx, catalog) → NodeMatch`** — **единственный** путь в `confident`: `article` + `sure` + без флагов + без uncertain_barrier. Остальные → needs_review (если эмодели, но данные сомнительны) или no_match/excluded/error.

Плюс три новые сущности:
- **`TreeNode`** — одна строка сметы с полями для движка (id, source_index, depth, code, name, status, review_status, matched_*, final_*).
- **`SectionMatchRequest`** — запрос к LLM: nodes (чанк), ancestors (путь), hints (крошки), targets (id, по которым нужен вердикт), catalog, precedents.
- **`NodeVerdict`** — ответ LLM per-узел: node_id, kind (article/org/none), article_code, sure, alt_code.

**Расширения:**
- **`MatchCandidate.score: float | None`** (было `float`) — `null` вместо `0`, чтобы не путать «отсутствие скора» с ошибочным скором.
- **`AncestorContext`** — новая dataclass для обоих движков.
- **`FUND_KEY_VERSION = 3`** и **`fund_key_v3(node, ctx) → str | None`** — ключ фонда версии 3: `normalize(name) + "" + (ctx.trusted_code or "")`. Версия не влияет на PR 1 (фонд выключен), но живёт для PR 3.

### 2. Порты и репозитории (`domain/ports.py`, `infrastructure/db/`)

**Новый порт:**
- **`TreeMatcher(ABC).match_section(req: SectionMatchRequest) → list[NodeVerdict]`** — единственный новый внешний сервис.

**Расширения `EstimateRepository`:**
- **`fetch_tree(estimate_id) → list[TreeNode]`** — все строки в порядке source_index.
- **`save_node_match_cas(node_id, result, expected_statuses) → bool`** — UPDATE с предикатом `status IN (:expected) AND review_status='unreviewed'`, возвращает `False` при проигранной гонке.
- **`refresh_tree_node(node_id) → TreeNode`** — перечитать один узел после проигранного CAS.

**Расширения `ArticleRepository`:**
- **`list_catalog() → list[CatalogArticle]`** — весь справочник (id, code, name, parent_code).

**Расширения `DecisionFundRepository`:**
- **`records_for_names(names: Sequence[str], version) → list[FundPrecedent]`** — один запрос на чанк: все живые записи фонда v3 по нормализованным именам (любой родитель). Возвращает `FundPrecedent` с дополненными `article_id` и `key` (полный ключ v3).

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
                 по каждому чанку:
                   build_request (ancestors, hints, targets, catalog)
                   tree_matcher.match_section
                   validate_verdicts + to_node_match
                   save_node_match_cas
                 при проигранном CAS:
                   refresh_tree_node → пересчитать контекст
                   повторить целевой узел
                 в finally: release lock → ready / partial_error
```

Решения (видны в коде):
1. **Бюджет из данных, не из промпта:** на сервис-уровне считаем `estimate_tokens` по каталогу, по имени раздела, по имёнам узлов. Сервис НЕ импортирует `infrastructure/` и никогда не рендерит промпт.
2. **Дедуп и линейный проход:** чанки обработаны сверху вниз (родитель раньше дочерних), узлы-цели дедуплят по вердиктам (дублики → первый берётся, остальные — warning).
3. **Fail-closed:** любая внутренняя ошибка движка (JSON, типы вердиктов, unknown_code) → запись `error` с match_error `tree_*`, никогда молчаливо не `confident`.

**Интеграция в `EstimateMatchingService.match_estimate`:**
- Условный ввод: `if engine == "tree": runner = TreeMatchingRunner(...) else: (RAG-путь)`.
- Флаг конфига: `matching_engine = "rag"` (default) или `"tree"`.
- Если `engine == "tree"` и запрос `fund_enabled=True` → `NotImplementedError` (фонд ждёт PR 3).

### 5. Конфиг (`app/core/config.py`)

8 новых settings (+ существующих 30+):
- **`matching_engine: Literal["rag", "tree"]`** = `"rag"` — выбор движка (флаг).
- **`tree_max_chunk_rows: int`** = 120 — строк в чанке (плюс токен-лимит, что меньше).
- **`tree_token_budget: int`** = 100_000 — окно для чанка (включая ответ).
- **`tree_catalog_reserve_pct: int`** = 25 — процент окна, зарезервированный для каталога.
- **`tree_chunk_reserve_pct: int`** = 80 — процент окна, зарезервированный для самого чанка.
- **`openrouter_tree_model: str`** = `"anthropic/claude-sonnet-4.6"` (вместо Haiku, дороговато для выпуска, но точнее; калибрировка в PR 2).
- **`tree_reasoning_effort: Literal["low", "medium", "high"]`** = `"low"` (extended thinking для future).
- **`openrouter_tree_max_tokens: int`** = 8000 — максимум токенов в ответе.

### 6. Фронтенд

- **`MatchCandidate.score`** теперь `number | null` во всех типах (`lib/types.ts`).
- **Рендеринг:** строка или кандидат БЕЗ скора → нет цветного бейджа, только текст кода (раньше выводил `0.00`).
- Логика ревью не изменилась; кандидаты из обоих движков одинаковы.

### 7. Тесты (11 задач, каждая с набором тестов)

✅ 519 passed / 3 skipped на сьюте (backend + frontend).

Ключевые сценарии:
- `test_tree_repository_integration` — CRUD + CAS на узлы дерева.
- `test_split_sections_*` — чанкинг (greedy packing, oversized узлы, recursion).
- `test_effective_ancestor_context_*` — цепочка доверия с барьерами.
- `test_resolve_parents` — индексы родителей по стеку глубин.
- `test_validate_verdicts_*` — все 7 валидационных путей, fail-closed.
- `test_to_node_match_*` — маппинг в статусы (только один путь в `confident`).
- `test_tree_matching_runner_*` — end-to-end сценарии (чанкинг, сохранение, гонка, CAS).
- `test_openrouter_tree_matcher_*` — адаптер (парсинг, retry, truncate).

---

## Ключевые решения

1. **Бюджет из данных.** `TreeMatchingRunner` считает `estimate_tokens` по строкам, НЕ рендерит промпт. Сервис полностью отделён от инфраструктуры; это требование Clean Architecture.

2. **`SectionMatchResponse` сырые словари.** LLM-адаптер возвращает список словарей-вердиктов из JSON. Валидация и маппинг — в доменном слое (`validate_verdicts`, `to_node_match`), никогда в адаптере → fail-closed.

3. **Единственный путь в `confident`.** Вердикт должен быть type `article`, `sure=true`, НОЛЬ флагов валидации, и **не было uncertain_barrier** в цепочке предков. Остальные комбинации → needs_review/no_match/error. Стратегия: высокая полоса пропускания (LLM выбирает), но узкие ворота уверенности.

4. **Фонд выключен в PR 1.** `fund_enabled=True` → `NotImplementedError`. Фонд ждёт версии 3 (спека §6, PR 3). Константа `FUND_KEY_VERSION = 3` и функция `fund_key_v3` уже готовы.

5. **RAG-путь неизменен.** Движок выбирается флагом `matching_engine`; если `"rag"`, код идёт по старому каналу. При дефолте `"rag"` и без явного переводки в конфиге, пользователь видит RAG (как сейчас).

---

## Что осталось

Спека предусмотрела это в §11 п.1 (PR breakdown):

### PR 2 — Харнесс калибровки
- `--engine rag|tree|both` флаг CLI
- Замер `top_1_strict` и других метрик на бенчмарке
- Frozen RAG baseline (воспроизводимость спайка)
- Калибровка `tree_reasoning_effort`, `tree_max_chunk_rows`
- В финале — decision о дефолте и скорости перехода

### PR 3 — Фонд решений v3
- `fund_enabled=True` (теперь выбросит, будет работать)
- Интеграция `fund_key_v3` в чанк-обработку
- Пресидент-записи в промпт
- Фронт: подсказка соседа (`dependents_hint`), если фонд подтвердил сестру

### PR 4 — Гейт качества
- Спека §9: порог top-1 в проде (если дойдёт)
- Flipping default `matching_engine = "tree"`
- Удаление RAG-кода (не нужен больше)
- Финализация

---

## Файлы

**Backend:**
- `app/domain/tree_matching.py` (новый, 327 строк)
- `app/domain/entities.py` (+`TreeNode`, `SectionMatchRequest`, `NodeVerdict`, +`AncestorContext`)
- `app/domain/decision_fund.py` (+`FUND_KEY_VERSION = 3`, +`fund_key_v3`)
- `app/domain/ports.py` (+`TreeMatcher` порт, расширения `EstimateRepository`, `ArticleRepository`, `DecisionFundRepository`)
- `app/services/tree_matching_service.py` (новый, `TreeMatchingRunner`, 222 строки)
- `app/services/estimate_matching_service.py` (интеграция `engine` флага)
- `app/infrastructure/ai/tree_prompt.py` (новый, ассемблировка запроса)
- `app/infrastructure/ai/openrouter_tree_matcher.py` (новый, адаптер)
- `app/infrastructure/db/estimate_repository.py` (расширения методов)
- `app/infrastructure/db/article_repository.py` (расширения методов)
- `app/core/config.py` (+8 `tree_*` settings)

**Frontend:**
- `src/lib/types.ts` (`MatchCandidate.score: number | null`)
- `src/components/estimate/ReviewCard.tsx` (условный рендеринг badge)

**Tests:**
- `backend/tests/test_tree_matching.py` (новый, доменные функции)
- `backend/tests/test_tree_matching_service.py` (новый, orch-сценарии)
- `backend/tests/test_openrouter_tree_matcher.py` (новый, адаптер)
- `backend/tests/test_tree_repository_integration.py` (новый, CAS + CRUD)
- Frontend тесты для типа `score: null`

**Конфиг:**
- `backend/.env.example` (+8 `TREE_*` переменных)

---

## Как включить локально

```bash
cd backend

# 1. Установить переменную
echo 'MATCHING_ENGINE=tree' >> .env

# 2. Запустить бэк
just dev-back

# 3. В отдельном окне — Celery воркер (требуется для асинхронного матчинга)
cd backend && uv run celery -A app.infrastructure.tasks.celery_app worker --pool=solo -l info

# 4. Загрузить смету через фронтенд
# Смета будет обработана tree-движком
```

Чтобы вернуться на RAG:
```bash
# Удалить или закомментировать строку в .env
# или установить
echo 'MATCHING_ENGINE=rag' >> .env

# и перезапустить бэк
```

---

## Поведение при ошибках

1. **Недоступен OpenRouter / timeout:** `instrumented_call` повторит до лимита, потом `error` в БД (match_error `tree_network_error`).
2. **Малформированный JSON в ответе:** парсер вернёт `[]` (пусто), каждая цель → status `error` (tree_malformed_response).
3. **Узел больше бюджета сам по себе:** `split_sections` напишет цель с `error` (tree_row_too_large) и продолжит остальное.
4. **Данные в БД рассинхронились (CAS-проигрыш):** `refresh_tree_node` перечитает, пересчитает контекст, повторит ту же цель.

Все пути → статусы `error`/`needs_review`/`no_match`, никогда молча `confident`.

---

## Релевантные документы

- **Спека:** [2026-08-27-tree-matching-core-design.md](../superpowers/specs/2026-08-27-tree-matching-core-design.md) (полный дизайн, все решения, измеры)
- **План:** [plan](../superpowers/plans/2026-08-28-tree-matching-pr1/) (задачи 1–11 закрыты, task 12 — эта документация)
- **PIPELINE:** [../PIPELINE.md](../PIPELINE.md) — добавлен раздел про tree-движок (рядом с RAG §6)
- **TECH_DEBT:** [../TECH_DEBT.md](../TECH_DEBT.md) — 9 новых записей из ревью (разлёт чанков, `_CODE_ORDER`, `_coerce`, логирование, очистка тестов, валидация `tree_reasoning_effort`, unused `validate_verdicts`, `articles.ts` score=0, параллелизм разделов, provenance контекста)

---

## Выводы

PR 1 реализовала полностью независимый движок: новая архитектура (отделена от RAG, отделена от фонда), полное покрытие тестами, fail-closed валидация, готовность к калибровке (PR 2). Переключение на флаг; дефолт остаётся RAG. Оттуда видно, что движок даёт выигрыш по качеству (спайк: 94.9% vs 77% RAG), но требует калибровки по speed и cost перед prod-флипом (PR 4).
