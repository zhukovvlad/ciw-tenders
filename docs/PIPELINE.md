# Пайплайн сопоставления смет (CIW)

> Сквозное описание решения: от постановки задачи до финального ревью оператором,
> с разбором архитектурных слоёв. Документ описывает систему **в том виде, как она
> работает сейчас**. Держать синхронным с кодом; точечные детали — по ссылкам на файлы.

---

## 1. Постановка задачи

«Автоматизатор строительных смет» загружает Excel-смету, отбирает строки видов работ
и через RAG (векторный поиск + LLM) сопоставляет каждую с эталонной статьёй справочника СМР.

**Что на входе:** `.xlsx`-смета с иерархией разделов (колонка `№ раздела`), наименованиями
(`Наименование раздела / позиции`) и типом раздела (`Вид раздела`).

**Что на выходе:** для каждого нумерованного узла-работы — рекомендованная статья справочника
с оценкой уверенности и одним из статусов: уверенное совпадение, требует проверки, нет совпадения.
Оператор проверяет спорные строки и выгружает результат в Excel.

**Ключевые свойства потока:**

- **Stateless по данным сметы** — смета нигде не хранится как доменная сущность дольше, чем нужно
  для обработки и ревью; персистентен только справочник (`template_articles`). Исходный файл лежит
  в объектном хранилище для повторной обработки/экспорта.
- **Асинхронный** — загрузка отвечает мгновенно (`201`), матчинг идёт фоном (Celery).
- **RAG** — retrieval (pgvector) + generation/арбитраж (LLM) с порогом уверенности между ними.
- **Асимметрия ошибок** — лучше лишний раз показать оператору сомнительную строку, чем молча
  выкинуть настоящую работу. Это правило пронизывает классификацию и трактовку отказов LLM.

---

## 2. Карта пайплайна (с высоты)

```
ФАЗА 0  Подготовка справочника (персистентна, вне потока сметы)
        импорт шаблона → template_articles (embedding=NULL) → воркер дозаполняет векторы

ФАЗА 1  Загрузка + парсинг сметы (синхронно, в HTTP-запросе)
        POST /estimates → валидация → парс Excel → MinIO + БД → enqueue Celery → 201

ФАЗА 2  Оркестрация матчинга (асинхронно, Celery)
        lock → running → классификация → эмбеддинг → gate справочника → матчинг → статус

ФАЗА 3  Ядро матчинга одного узла (RAG)
        retrieval top-K → порог 0.90 → LLM-арбитр → NodeMatch

ФАЗА 4  Финализация статуса сметы
        ready / partial_error / blocked + лог-summary

ФАЗА 5  Ревью оператором + экспорт
        confirm / override / reject → выгрузка Excel
```

---

## 3. Фаза 0 — подготовка справочника

Без готового справочника матчинг не стартует (его проверяет gate в фазе 2).

1. **Импорт шаблона.** Excel справочника →
   [template_parser.py](../backend/app/services/template_parser.py) → дельта-план
   [import_planning.py](../backend/app/services/import_planning.py) → таблица `template_articles`.
   Каждая статья получает `embedding_input` (крошка `предок. предок. имя`) и `embedding = NULL`.
2. **Векторизация воркером.** `just embed-worker` (или Celery `embed_articles_task`,
   [tasks.py](../backend/app/infrastructure/tasks/tasks.py)) → дозаполняет вектор через
   `OpenRouterEmbedder` (модель `google/gemini-embedding-2`, `dim=768`,
   [openrouter_embedder.py](../backend/app/infrastructure/ai/openrouter_embedder.py)).
   Запись — **compare-and-swap** по `embedding_input`: вектор пишется, только если текст не менялся.
   Векторный поиск исключает строки с `embedding IS NULL`.

> Справочник «org-free»: крошки статей не содержат организационного контекста (этапы/корпуса).
> Поэтому смета перед матчингом тоже очищается от орг-токенов — иначе векторы не сопоставимы.

---

## 4. Фаза 1 — загрузка и парсинг сметы

`POST /estimates` → [estimates.py](../backend/app/api/routes/estimates.py):

1. **Валидация на входе:** расширение `.xlsx`, лимит размера (`estimate_max_upload_mb`),
   сигнатура ZIP `PK\x03\x04` (реальный xlsx — это zip).
2. **Ingest** ([estimate_service.py](../backend/app/services/estimate_service.py)):
   - **Парсинг** ([estimate_parser.py](../backend/app/services/estimate_parser.py)):
     `bytes → ParsedEstimate`. Дерево строится по `№ раздела` (читается **строкой**, иначе
     `1.10` схлопнулось бы в `1.1`). Нумерованные строки → `EstimateNode` (единица матчинга);
     строки с `№ = NaN` → `EstimatePosition` (контекст, не матчатся). `embedding_input` узла —
     крошка предков `. имя`, собранная **тем же правилом, что и справочник** (критично для retrieval).
     Нет обязательных колонок → `ValueError` → `422` *до* записи куда-либо.
   - **MinIO:** исходный файл кладётся в объектное хранилище (`estimates/<uuid>/<filename>`).
     Сбой хранилища → `503`, БД не тронута.
   - **БД:** создаётся `estimate` + узлы со `status='pending'`, `embedding=NULL`.
   - **Постановка задачи:** `enqueue_match` строго *после* коммита. Брокер недоступен →
     best-effort (смета остаётся `pending`, лечится ручным ре-триггером). Ответ `201` сразу.

---

## 5. Фаза 2 — оркестрация матчинга

Celery-задача `match_estimate_task` ([tasks.py](../backend/app/infrastructure/tasks/tasks.py)) —
тонкая обёртка вокруг брокера. Она пиннит **один** коннект (`engine.connect()` +
`SessionLocal(bind=conn)`), чтобы session-level advisory-lock пережил коммиты (иначе на
prefork-конкурентности лок утёк бы вместе с возвратом коннекта в пул).

Вся логика — в [EstimateMatchingService.match_estimate](../backend/app/services/estimate_matching_service.py):

1. **Lock** (`try_matching_lock`, advisory) — конкурент уже обрабатывает → no-op.
2. **`status = running`** (коммит до тяжёлых шагов — виден сразу).
3. **Классификация узлов** — отсечь организационные заголовки («Этап 1», «Корпус 5», «ЖК …»),
   чтобы не матчить мусор. Каскад из трёх проходов
   ([_classify_nodes](../backend/app/services/estimate_matching_service.py),
   домен — [classification.py](../backend/app/domain/classification.py)):
   - *Проход 1 — лексика* (`classify_lexical`): нет орг-токена → `WORK`; орг-токен + есть
     содержательная «голова»-работа → `UNSURE`; чистый орг-токен → `ORG`.
   - *Проход 1b — LLM по UNSURE*: дешёвая модель `claude-haiku-4.5` батчами
     ([openrouter_classifier.py](../backend/app/infrastructure/ai/openrouter_classifier.py)).
     Любой сбой / битый JSON / несовпадение длины → весь батч `UNSURE`
     (**асимметрия ошибок: никогда не `ORG` молча**).
   - *Проход 2 — структурный override + крошка*: `ORG` исключается (`status='excluded'`),
     **кроме** листа с non-org предком — это работа, разбитая по корпусам/этапам, чьё имя
     случайно совпало с орг-токеном (`is_excluded`). `build_embedding_input` пересобирает крошку,
     выбрасывая ORG-предков и собственный орг-токен. Запись — одним bulk-коммитом, с охраной
     статуса (терминальные/отревьюенные строки не трогает).
4. **Эмбеддинг узлов** (`_embed_nodes`): чанками по 100, тем же `OpenRouterEmbedder`. Транзиентный
   сбой → узел остаётся `pending` (доберётся ре-триггером). Между чанками — heartbeat (`touch`).
5. **Gate готовности справочника** (`matching_readiness`): если статей нет (`total==0`) или есть
   невекторизованные (`pending>0`) → `DictionaryNotReadyError`. Обёртка ретраит
   (`gate_retry_max` / backoff); при исчерпании попыток → `status='blocked'`.
6. **Матчинг узлов** (`_match_nodes`): по каждому matchable-узлу
   (`status ∈ {pending, error, no_match}`, есть вектор, `review_status='unreviewed'`) вызывается
   ядро матчинга (фаза 3). Результат пишется через `save_node_match` с CAS
   `WHERE review_status='unreviewed'` — ручные правки оператора не перетираются.

---

## 6. Фаза 3 — ядро матчинга одного узла (RAG)

[MatchingService.match_one](../backend/app/services/matching_service.py) принимает **готовый вектор**
узла (повторно не эмбеддит) и его текст (нужен только LLM-арбитру):

1. **Retrieval:** `search_similar(embedding, top_k)`
   ([article_repository.py](../backend/app/infrastructure/db/article_repository.py)) — pgvector,
   `score = 1 − cosine_distance`, строки с `embedding IS NULL` исключены. Пусто → **`NO_MATCH`**.
2. **Порог уверенности:** `best.score > 0.90` → **`CONFIDENT`** (LLM не зовём).
3. **LLM-арбитр** иначе ([openrouter_matcher.py](../backend/app/infrastructure/ai/openrouter_matcher.py),
   модель `claude-sonnet-4.6`, `temperature=0`): на вход — наименование работы + список
   кандидатов **без кодов** (код провоцирует эхо кода вместо номера); просим вернуть **номер строки**
   ([llm_matching_common.py](../backend/app/infrastructure/ai/llm_matching_common.py)).
   - Ответ `0` / нечитаемо / индекс вне диапазона → отказ (`None`).
   - **Анти-галлюцинация:** выбранная статья валидируется — обязана быть среди кандидатов
     (`_score_of`); «придуманная» статья трактуется как отказ.
   - Выбор есть → **`NEEDS_REVIEW`** (со score выбранного кандидата); отказ → **`NO_MATCH`**.

Возвращается `NodeMatch`: статус + matched_* + score + **снимок всех кандидатов** (замораживается
для ревью в фазе 5).

**Статусы узла (развилки):**

| Статус | Когда |
|---|---|
| `excluded` | орг-заголовок, исключён из матчинга (обратимо) |
| `confident` | `score > 0.90`, без LLM |
| `needs_review` | LLM выбрал кандидата из топ-K |
| `no_match` | пустой retrieval или отказ LLM |
| `error` | транзиентный сбой адаптера исчерпал бюджет ретраев |

---

## 7. Фаза 4 — финализация статуса сметы

После прохода матчинга
([estimate_matching_service.py](../backend/app/services/estimate_matching_service.py)):

- есть узлы в `error` или незавершённые (`pending`) → **`partial_error`** (с detail-счётчиками);
- иначе → **`ready`**.

Пишется лог-summary (`confident / needs_review / no_match / error / excluded / latency_ms`).
Lock снимается в `finally`.

**Восстановление после краша:** если воркер умер с `SIGKILL` на тайм-лимите, смета зависает в
`running`. При ручном ре-триггере `POST /estimates/{id}/match`
([estimates.py](../backend/app/api/routes/estimates.py)) sweeper на выделенном коннекте берёт
advisory-лок как арбитр живости (занят → воркер жив → no-op) и сбрасывает `running → pending`,
после чего задача ставится заново.

---

## 8. Фаза 5 — ревью и экспорт

- `GET /estimates/{id}` — оператор видит результат с замороженными кандидатами по каждой строке.
- `PATCH /estimates/{id}/rows/{row_id}/review`
  ([estimate_review_service.py](../backend/app/services/estimate_review_service.py)) —
  решения `confirm` (согласие с AI) / `override` (другой кандидат или ручной подбор) / `reject`
  («статьи нет»). Ось `review_status` **независима** от AI-снимка (`status`) и авторитетна:
  оператор может передумать, AI-снимок при этом не меняется. Отревьюенные строки защищены от
  перематчинга (CAS в `save_node_match`).
- `GET /estimates/{id}/export`
  ([estimate_export_service.py](../backend/app/services/estimate_export_service.py)) — выгрузка
  результата в Excel; `strict=true` требует, чтобы все спорные строки были разобраны.

---

## 9. Архитектурные слои (Clean Architecture)

Направление зависимостей строгое: **`api → services → domain ← infrastructure`**.
Доменный слой не зависит ни от чего; внешние слои зависят от абстракций (портов).

```
HTTP
 │
 ▼
api/routes ─ DTO-схемы, валидация запроса, маппинг ошибок → HTTP-коды
 │           DI собирается в api/deps.py (composition root)
 ▼
services ─ сценарии (use cases): ingest, оркестрация матчинга, ядро матчинга,
 │         классификация-оркестрация, ревью, экспорт. Зависят ТОЛЬКО от портов.
 ▼
domain ─ entities.py (сущности), ports.py (абстракции), classification.py
 ▲       (чистая логика классификации). БЕЗ импортов FastAPI/SQLAlchemy/SDK.
 │
infrastructure ─ реализации портов: pgvector-репозитории, OpenRouter
                 (embedder/matcher/classifier), MinIO, Celery, JWT/argon2.
                 Здесь живут все внешние SDK/HTTP.
```

### Слой за слоем

- **`domain/`** ([entities.py](../backend/app/domain/entities.py),
  [ports.py](../backend/app/domain/ports.py),
  [classification.py](../backend/app/domain/classification.py)) — сердце системы. Сущности
  (`EstimateNode`, `TemplateArticle`, `NodeMatch`, `WorkClass`, статусы) и порты-интерфейсы
  (`ArticleRepository`, `Embedder`, `LLMMatcher`, `WorkTypeClassifier`, `EstimateRepository`,
  `ObjectStorage`, `TaskQueue` и др.). Чистый Python, без внешних зависимостей.
- **`services/`** — оркестрация без знания о конкретных технологиях:
  [estimate_service.py](../backend/app/services/estimate_service.py) (ingest),
  [estimate_matching_service.py](../backend/app/services/estimate_matching_service.py) (оркестрация
  матчинга сметы), [matching_service.py](../backend/app/services/matching_service.py) (ядро
  матчинга узла), [estimate_review_service.py](../backend/app/services/estimate_review_service.py),
  [estimate_export_service.py](../backend/app/services/estimate_export_service.py).
- **`infrastructure/`** — адаптеры портов: БД (SQLAlchemy + pgvector,
  [article_repository.py](../backend/app/infrastructure/db/article_repository.py),
  [estimate_repository.py](../backend/app/infrastructure/db/estimate_repository.py)),
  AI ([openrouter_*.py](../backend/app/infrastructure/ai/)), хранилище
  ([s3_object_storage.py](../backend/app/infrastructure/storage/s3_object_storage.py)),
  очереди ([tasks/](../backend/app/infrastructure/tasks/)), auth.
- **`api/`** — FastAPI: роуты ([routes/](../backend/app/api/routes/)), DTO-схемы
  ([schemas.py](../backend/app/api/schemas.py)), DI-сборка в
  [deps.py](../backend/app/api/deps.py). DTO ≠ доменные сущности.

### Правила, которые держат архитектуру

- Новая зависимость от внешнего сервиса → **сначала порт** в `domain/ports.py`, потом реализация
  в `infrastructure/`.
- Бизнес-логику не писать в роутах и репозиториях — её место в `services/`.
- DTO и доменные сущности не смешивать.
- AI-вызовы инструментируются через `instrumented_call`
  ([_instrumented.py](../backend/app/infrastructure/ai/_instrumented.py)) — один summary на вызов
  (provider/model/latency/attempts/outcome), ретраи транзиентов внутри.

---

## 10. Поток данных одним взглядом

```
Excel-смета
  → ParsedEstimate {nodes, positions, warnings}        (estimate_parser)
  → estimate_rows: status=pending, embedding=NULL       (БД) + файл в MinIO
  → классификация: WORK/ORG/UNSURE → excluded?,         (classification + LLM-classifier)
                   embedding_input (org-free крошка)
  → embedding: vector(768)                              (OpenRouterEmbedder)
  → [gate: справочник готов?]
  → retrieval top-K (pgvector, cosine)                  (article_repository.search_similar)
  → score>0.90 ? confident
              : LLM-арбитр выбирает из топ-K → needs_review / no_match
  → NodeMatch {status, matched_*, score, candidates[]}  (save_node_match, CAS)
  → estimate: ready / partial_error / blocked
  → ревью оператора: confirm / override / reject        (review_status, независимая ось)
  → экспорт в Excel
```

---

## Связанные документы

- [TECH_DEBT.md](TECH_DEBT.md) — отложенные задачи и качество матчинга.
- [devlog/](devlog/) — журнал работ по задачам.
- [CLAUDE.md](../CLAUDE.md) — краткие указания по репозиторию (источник правды по командам/конвенциям).
