# Tech Debt

Реестр технического долга проекта. Живой документ: при появлении долга — добавь строку,
при погашении — удали (или помести в «Погашено» с датой). Каждый пункт: что, почему отложено,
как чинить, ссылки.

Приоритеты: 🔴 high (ломает/блокирует развитие) · 🟡 medium (мешает, но обходимо) · 🟢 low (полировка).

---

## 🟢 SP2-матчинг: пул коннектов vs concurrency воркера + drain на каждый `create_article`

**Что:** (1) `engine` на дефолтном QueuePool (5+10). Каждая running-задача пинит коннект до
`task_time_limit_s`=660s. Dev-воркер `--pool=solo` (concurrency 1) — безопасно, но прод с
`prefork concurrency>1` + коннекты FastAPI-запросов могут исчерпать пул. (2) `create_article`
энкьюит полный drain справочника на каждое добавление (singleton-лок + drain-to-zero делают это
безопасным, но при массовом добавлении через API — N почти-no-op задач).

**Как чинить:** (1) задокументировать/выставить `pool_size` относительно concurrency воркера перед
масштабированием за пределы `--pool=solo`; (2) при необходимости — дебаунс/батч enqueue эмбеддинга.
См. [session.py](../backend/app/infrastructure/db/session.py), [articles.py](../backend/app/api/routes/articles.py).

---

## 🟡 Alembic autogenerate шумит на `Vector`/HNSW

- **Что:** при будущих `just makemigration` автогенерация некорректно интроспектит тип `Vector` и
  HNSW-индекс → ложные drop/create индекса.
- **Как чинить:** добавить `include_object`/`include_name`-фильтр в
  [alembic/env.py](../backend/alembic/env.py) при первой реальной автогенерации. Для `0001` неактуально
  (написана руками).

## 🟡 Воркер эмбеддингов запускается только вручную

- **Что:** воркер эмбеддингов ([embed_worker.py](../backend/app/scripts/embed_worker.py),
  очередь = `template_articles` с `embedding IS NULL`) — отдельный CLI, поднимается только
  руками (`just embed-worker [--once] [--batch-size N]`). Бэкенд (`just dev-back` = uvicorn)
  его не стартует; в [main.py](../backend/app/main.py) нет ни startup-хука, ни фоновой
  задачи/потока.
- **Почему отложено:** прогон дёргает платный эмбеддер (OpenRouter) и ходит в сеть, поэтому
  на этапе template-ingestion сознательно оставили ручным, чтобы не жечь токены на каждый
  старт/импорт. Но после загрузки/изменения справочника новые строки висят с `embedding IS NULL`,
  пока кто-то не вспомнит запустить воркер — это легко забыть (см. смоук catalog-admin-ui:
  импорт прошёл, а матчинг бы молча работал по неполному индексу).
- **Последствия:** RAG-сопоставление смет идёт по справочнику без свежих эмбеддингов до
  ручного прогона. На отображение справочника и сам импорт не влияет.
- **Как чинить (выбрать подход):**
  - **По расписанию:** периодический прогон `run_once` (cron / APScheduler / системный таймер)
    — просто, но есть лаг и пустые проходы (хотя `run_once` дёшев, если очередь пуста:
    `fetch_pending` вернёт `[]` и эмбеддер не вызывается).
  - **По событию обновления таблицы:** триггерить дозаполнение при изменении `template_articles`
    (insert/update со сбросом `embedding=NULL`). Варианты: после `import_template`/manual-create
    в сервисе ставить задачу в очередь (FastAPI BackgroundTasks / отдельный воркер-процесс,
    читающий из БД-очереди); либо PG `LISTEN/NOTIFY` на изменение таблицы → воркер реагирует.
    Учесть: эмбеддинг должен оставаться вне HTTP-запроса (платный + долгий), идемпотентным и
    переживать сбой (как сейчас — CAS-апдейт по `id AND embedding_input`).
  - В любом варианте сохранить ручной `--once` для бэкофилла/отладки.
- **Связано:** [embedding_worker.py](../backend/app/services/embedding_worker.py) (`run_once`,
  батч 100), [embedding_queue_repository.py](../backend/app/infrastructure/db/embedding_queue_repository.py).

## 🟢 `GET /api/articles` — мягкий потолок `limit=1000`

- **Что:** листинг справочника отдаёт до `limit` строк, дефолт поднят до 1000 (справочник
  сейчас 362). Если когда-нибудь перевалит за 1000 — листинг начнёт молча обрезаться.
- **Почему отложено:** на текущую задачу (загрузка + эмбеддинг) не влияет; фронт-экрана
  дерева пока нет.
- **Как чинить:** при реализации фронт-экрана дерева — курсорная/постраничная подгрузка
  вместо одного большого запроса. См. план
  [docs/superpowers/plans/2026-06-21-template-ingestion.md](superpowers/plans/2026-06-21-template-ingestion.md), Task 2.

## 🟢 Осиротевшие объекты MinIO после сбоя при удалении сметы

- **Что:** при удалении сметы сервис сначала удаляет запись из БД (`EstimateRepository.delete`),
  затем удаляет файл из MinIO (`ObjectStorage.delete`, best-effort). Если процесс упадёт
  между двумя операциями (crash, OOM, перезапуск пода), объект в MinIO останется без ссылки
  из БД — «сирота». Обратная схема (сначала MinIO, потом БД) не лучше: при сбое смета
  исчезнет из хранилища, но запись в БД сохранится.
- **Почему отложено:** вероятность сбоя в узком окне мала; объём одного файла незначителен.
  Реализация реапера требует отдельной фоновой задачи или хранения «soft-delete» пометки
  в БД (tombstone) — выходит за рамки текущего спринта.
- **Как чинить:** добавить периодический реапер (cron / APScheduler / pg `LISTEN/NOTIFY`),
  который сканирует MinIO bucket и удаляет объекты, чьи ключи отсутствуют в `estimates.original_object_key`.
  Альтернатива — хранить tombstone (`deleted_at`) и удалять объект из MinIO синхронно
  после успешного мягкого удаления из БД, затем физически чистить по расписанию.
- **Связано:** `EstimateService.delete` (Task 5), `S3ObjectStorage.delete`,
  `SqlAlchemyEstimateRepository.delete`.

## 🟢 Полировка из финального ревью авторизации

- **Тесты:** нет теста «инвалид/просроченный токен → 401» на `GET /api/auth/me` (есть только «нет токена»);
  `test_create_user_anonymous_401` не проверяет заголовок `WWW-Authenticate` (основной гвард на `/me` — проверяет);
  `test_user_repository_mapping` не ассертит `created_at`/`password_hash`.
- **Фейк:** `FakeUserRepository.add` ([fakes.py](../backend/tests/fakes.py)) не enforce-ит уникальность
  email (реальный репозиторий — через UNIQUE) → дубль-инсерт в логике сервиса фейк не поймает.
- **Мелочи:** `UserOut.from_entity` `id=user.id or 0` — молчаливый sentinel (для персистнутого юзера
  недостижим, но лучше падать явно); `JwtTokenService.issue` без гварда на `User.id is None`;
  таблица команд в [CLAUDE.md](../CLAUDE.md) не содержит `just migrate*` (в прозе есть);
  лишний `CREATE EXTENSION` в [neon-database-setup.md](instructions/neon-database-setup.md) (ревизия `0001`
  уже его делает); порядок импортов в `alembic/script.py.mako` (ruff I001 на сгенерированных ревизиях).

## 🟢 SP3: нет несклип-CI-теста раунд-трипа парсер→экспортёр (страж офсета `+2`)

- **Что:** экспорт пишет код по физ.строке `source_index + 2` — инвариант держится, **пока** SP1-парсер
  не меняет чтение (`read_excel`: заголовок в строке 1, без `skiprows`/`header=`/`dropna`/`reset_index`).
  Сейчас офсет страхуют два **раздельных** теста: парсер ассертит `source_index==33` для узла `1.1.5`,
  но только при наличии приватного golden-файла (`skipif`, в CI **не** гоняется); экспорт-тест ассертит
  `source_index=33 → физ.строка 35` на рукотворном workbook. Цепочки «выход парсера → вход экспортёра»
  в одном несклип-тесте нет: добавит кто-то `skiprows`/`header=` — CI останется зелёным, экспорт молча
  поедет в соседние ячейки.
- **Почему отложено:** связка задокументирована (docstring `estimate_export_service.py`, коммент парсера);
  оба конца по отдельности покрыты; вероятность незаметной правки SP1-чтения низка. Выявлено финальным
  ревью SP3.
- **Как чинить:** добавить несклип раунд-трип-тест на синтетическом `.xlsx`: parse → export → ассерт
  ячейки. См. [estimate_export_service.py](../backend/app/services/estimate_export_service.py),
  [estimate_parser.py](../backend/app/services/estimate_parser.py).

## 🟢 SP3-фронт: прод-код импортит тип из мок-модуля + тихий no-op экспорта/правки

- **Что:** (1) `EstimateFlow.tsx` импортит `type Progress` из `@/lib/mock/api` — связка прод-потока с
  тест-фикстурным модулем, от которого SP3 как раз уходит (тип стирается на сборке, рантайм-связки нет,
  но смысловая есть). (2) `handleReview` молча `return`-ит при `estimateId === null`, хотя оптимистичный
  dispatch уже сработал → строка показана «подтверждённой», но на бэк не уехала (прикрыто регидрацией
  `estimateId` из sessionStorage; достижимо только при битом session-storage).
- **Почему отложено:** косметика/край; на нормальном потоке не воспроизводится. Выявлено финальным ревью SP3.
- **Как чинить:** (1) вынести `Progress` в `@/lib/types` или объявить локально в `estimates.ts`;
  (2) в null-ветке `handleReview` добавить `reopen` + `toast.error` (как в `.catch`-ветке PATCH).
  См. [EstimateFlow.tsx](../frontend/src/pages/estimate/EstimateFlow.tsx).

## 🟢 Pluggable LLM provider — полировка из ревью (тест-гигиена)

- **Что:** мелочи, выявленные ревью PR #8 (не блокеры, на корректность не влияют):
  - `test_system_prompt_requires_row_number_and_refusal_channel` ([test_llm_matching_common.py](../backend/tests/test_llm_matching_common.py))
    ассертит только `"0" in SYSTEM_PROMPT` — слабый гейт: не пинит инструкцию «номер строки, а не код»,
    регрессия с удалением этой инструкции не будет поймана (сам промпт корректен).
  - `_FakeClient.post(self, url, headers, json)` ([test_openrouter_matcher.py](../backend/tests/test_openrouter_matcher.py))
    позиционная сигнатура; прод зовёт `headers=`/`json=` по имени, так что тесты проходят, но фейк
    вводит в заблуждение про порядок аргументов. Сделать `def post(self, url, *, headers, json)`.
  - `_raise_body_error` ([openrouter_matcher.py](../backend/app/infrastructure/ai/openrouter_matcher.py))
    аннотирован `-> None`, но всегда бросает — точнее `-> typing.Never`.
- **Почему отложено:** косметика/тест-гигиена; сьют зелёный, поведение корректно. Кандидаты на попутную
  чистку при следующем касании этих файлов.
- **Связано:** PR #8 (CodeRabbit-ревью), финальное whole-branch ревью под-проекта.

---

## Сознательно вне объёма (не долг, а план на будущее)

Решено не делать в текущей итерации авторизации (см. спек, раздел «Вне объёма»):

- Refresh-токены, logout / блэклист токенов (пока access-only + `is_active`).
- Rate-limit / лок-аут на `POST /api/auth/login`.
- Сброс и смена пароля; самостоятельная регистрация.
- Фронтенд: страница логина, хранение токена, гварды роутов (бэкенд даёт готовый API).
- Перевод `/api/estimates/match` на отдачу Excel-файла; вынос обогащения смет в фоновые задачи.
- Google-адаптер LLM-арбитра матчинга (порт `LLMMatcher` готов к ещё одному провайдеру) — не делался
  в под-проекте pluggable-llm-provider; добавляется по той же схеме, что `OpenRouterLLMMatcher`.

---

## Погашено

- **🟡 SP2: статус `running` не самовосстанавливается после жёсткого краша воркера** — закрыто SP3
  staleness-sweep'ом (2026-06-23, ветка `feat/estimate-review-export`). `POST /api/estimates/{id}/match`
  перед enqueue: при `status='running'` и `now-updated_at > task_time_limit_s` (660s) берёт advisory-лок
  как арбитр живости (взялся → прежний держатель мёртв → `running→pending`; занят → воркер жив → no-op).
  Sweeper на **выделенном коннекте** (`bind=conn`, как `tasks.py`): `try_lock→set_status(commit)→release`
  на одном коннекте, лок не течёт. `detail` ре-триггера стал честным («перезапущено после сбоя» /
  «уже выполняется» / «поставлено в очередь»). Тесты `test_estimate_sweep.py` (юнит) +
  `test_sweep_lock_integration.py` (opt-in, страж против регрессии утечки лока). См. devlog
  [2026-06-23-estimate-review-export.md](devlog/2026-06-23-estimate-review-export.md).
- **🟡 SP2: узкий перехват исключений в embed/match (смета залипала в `running`)** — закрыто по
  комментарию Copilot к PR #7 (2026-06-23). В `match_estimate` добавлен top-level `except` (не gate,
  не transient) → `PARTIAL_ERROR` с деталью перед re-raise; `DictionaryNotReadyError` по-прежнему
  пробрасывается для gate-retry. Лок отпускается в `finally`. Остаётся только жёсткий краш (см. живой
  пункт про staleness выше). Тест `test_unexpected_error_sets_partial_error_and_reraises`.
- **🟢 SP2: churn AI-клиентов на воркере** — закрыто по комментарию Copilot к PR #7 (2026-06-23).
  `build_estimate_matching_service` берёт `get_embedder()`/`get_llm_matcher()` (кэшированные синглтоны)
  вместо создания нового `httpx.Client`/Anthropic-клиента на каждую задачу и gate-retry; `build_embedder`
  удалён, репозитории по-прежнему строятся на пиннутой сессии задачи.
- **🔴 ORM `TemplateArticleModel` расходился со схемой (иерархия)** — закрыто фичей template-ingestion
  (PR #3). `models.py` теперь на дереве: `parent_id` (self-FK), `embedding_input`, `embedding` (VECTOR);
  `section_name` удалён везде. `article_service`/матчинг/репозиторий/DTO переведены на дерево.
