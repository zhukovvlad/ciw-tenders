# SP2: асинхронный матчинг смет (Celery) + честный score — Design

**Статус:** дизайн принят в брейншторме (2026-06-23), готов к плану реализации.
**Зависит от:** SP1 (загрузка/хранение сметы + иерархический парсер) — влит в `main` (PR #6).
**Предшествует:** SP3 (ревью/правки + запись `Статья СМР` обратно в `.xlsx`).

## Контекст и место в дорожной карте

- **SP1 (готово):** Excel-смета → иерархический парсер → узлы в `estimate_rows`
  (`status='pending'`, `embedding=NULL`), исходный файл в MinIO. Матчинга нет.
- **SP2 (этот документ):** асинхронный матчинг. Воркер эмбеддит `pending`-узлы и
  сопоставляет их со справочником (порог→LLM-арбитр), пишет иммутабельный снимок
  статьи + честный `score`, ведёт статусы строк и сметы. Сюда же — перевод эмбеддинга
  справочника на тот же механизм (единый воркер) и снятие старого синхронного пути.
- **SP3 (позже):** ревью/правки матчей, запись `Статья СМР` обратно в файл по
  `source_index`, выгрузка `.xlsx`.

Сметы по-прежнему персистентны (узлы матчатся, не пересоздаются); справочник
(`template_articles`) — источник кандидатов.

## Цель и границы

### В объёме SP2

- Celery-приложение + Redis-брокер (managed Redis на Timeweb), **единый воркер** на
  два типа задач: `match_estimate(estimate_id)` и `embed_articles()`.
- Перевод эмбеддинга справочника с ручного `just embed-worker` на Celery-задачу
  `embed_articles()` + явный триггер (админский endpoint + хук импорта/добавления).
- Матчинг узлов сметы: идемпотентный батч-эмбед `pending`-узлов → gate готовности
  справочника → поузловой матч (порог→LLM-арбитр) → запись иммутабельного снимка
  статьи (`matched_*`/`score`/`candidates`) + статусы строк, агрегатный статус сметы.
- Миграция `0004`: колонки снимка на `estimate_rows`, `status_detail` на `estimates`.
- Эндпоинт ре-триггера матчинга сметы; админский эндпоинт эмбеддинга справочника.
- Снятие синхронного `POST /estimates/match`, старого `ExcelEstimateParser`,
  `EstimateRow`-пути, `MatchingService.match_row/match_rows`, рус. енума `MatchStatus`,
  команды `just embed-worker` и скрипта `embed_worker.py`.

### Вне объёма (SP2/SP3 и далее)

- Авто-перематчинг смет при изменении справочника — **нет** (снимок иммутабелен).
- Авто-резюм матчинга по готовности справочника — **нет** (выбран `blocked` + ручной
  ре-триггер).
- Поля ревью/правки, запись `Статья СМР` обратно, выгрузка `.xlsx` → **SP3**.
- Эмпирическая перекалибровка порога `0.90` под сметы, отсечение «структурных» предков
  → позже, по флагам/score.
- **Реапер «зависших `running`»** (смета, чей воркер умер; восстановление в SP2 — ручной
  ре-триггер) и **реапер сирот MinIO** → тех-долг ([docs/TECH_DEBT.md](../../TECH_DEBT.md)).
- Celery beat / расписание; фронтенд-экраны истории/просмотра/ревью.

## Архитектура (Clean Architecture сохраняется)

Направление зависимостей: `api → services → domain ← infrastructure`. Celery и Redis —
внешняя инфраструктура, живут в `infrastructure/`; домен и сервисы их не знают.

```
api ─┐
     ├─► services (чистые: matching, estimate_matching, embedding) ──► domain (ports)
     │                                                                     ▲
infrastructure ──► Celery app + tasks + CeleryTaskQueue ─────────────────┘
                   (тонкие обёртки: сессия → сервис из портов → коммит)
```

- **Порт `TaskQueue`** (`domain/ports`): `enqueue_match(estimate_id) -> None`,
  `enqueue_articles_embed() -> None`. Методы возвращают `None` (не task-id) — чтобы
  никто не завязался на результат и абстракция не потекла. API/сервисы зависят только
  от порта.
- **Celery — в `infrastructure/tasks/`**: приложение (`celery_app`), определения задач
  (тонкие: открыть сессию → собрать сервис из портов → вызвать → закоммитить),
  адаптер `CeleryTaskQueue(TaskQueue)` (`.delay(...)`).
- **Источник правды — Postgres.** Result backend Celery **не используется** (задачи
  fire-and-forget пишут результат в БД). Брокер — `CELERY_BROKER_URL`/`REDIS_URL` из
  `backend/.env`.
- **Пулы и очереди (осознанно):**
  - **dev (Windows):** `--pool=solo`, одна FIFO-очередь — всё сериализовано, порядок
    задаёт оператор; длинный `embed_articles` блокирует матчи (head-of-line) — принято
    на текущем масштабе.
  - **прод (Linux/Timeweb):** `--pool=prefork --concurrency=N`; `embed_articles`
    маршрутизируется в **отдельную очередь**, чтобы долгий эмбеддинг справочника не делал
    head-of-line-блокировку матчей. Per-estimate advisory-lock делает concurrency
    безопасным (см. «Конкурентность»).
- **Windows-нюанс:** prefork на Windows не работает → dev-воркер
  `uv run celery -A app.infrastructure.tasks worker --pool=solo`. Фиксируется в justfile.

## Потоки эмбеддинга (независимы)

Эмбеддинг справочника и эмбеддинг узлов сметы — **две независимые операции**; ни одна
не ждёт другую. Матчинг — точка их соединения и требует, чтобы оба были полностью готовы.

- **Эмбеддинг справочника** (`template_articles`): задача `embed_articles()`.
  Идемпотентна: эмбеддит только `embedding IS NULL`, чанками, инкрементальные коммиты,
  CAS по `embedding_input` (как в SP1). **Замена-триггер** ручному `just embed-worker`
  (обязательна, иначе справочник никогда не проэмбеддится и всё уйдёт в `blocked`):
  - админский **`POST /api/articles/embed`** ставит задачу `embed_articles()`;
  - пути **импорта/добавления** статей зовут `TaskQueue.enqueue_articles_embed()`.
- **Эмбеддинг узлов сметы**: под-операция `embed_estimate_nodes(estimate_id)` **внутри**
  `match_estimate` (не отдельная Celery-задача — это снимает риск двойного эмбеддинга).
  Эмбеддит только узлы с `embedding IS NULL`.

## Задача `match_estimate(estimate_id)`

Единственная задача стороны сметы. Псевдокод (контракт; точная реализация — в плане):

```python
def match_estimate(self, estimate_id: int) -> None:
    if not self._estimates.try_matching_lock(estimate_id):
        return                                          # конкурент владеет → no-op
    try:
        was_running = self._estimates.status_is_running(estimate_id)
        self._estimates.set_status(                     # COMMIT до embed-шага
            estimate_id, RUNNING,
            detail="восстановление после обрыва" if was_running else None,
        )
        # 1) embed-шаг: идемпотентно, keyset-курсором, чанк-коммиты, CAS
        last_id = 0
        while chunk := self._estimates.fetch_unembedded_nodes(estimate_id, after_id=last_id, limit=CHUNK):
            vecs = self._embedder.embed_batch([n.embedding_input for n in chunk])  # строго len, по порядку
            for n, v in zip(chunk, vecs, strict=True):
                self._estimates.save_node_embedding(n.id, n.embedding_input, v)    # CAS-commit
            last_id = chunk[-1].id                       # курсор вперёд → тот же id не вернётся
        # 2) gate: усиленный (пустой справочник != готов)
        total, pending = self._articles.matching_readiness()
        if total == 0 or pending > 0:
            self._estimates.set_status(estimate_id, BLOCKED,
                                       detail=f"справочник не готов: total={total} pending={pending}")
            return
        # 3) match-шаг: только {pending, error, no_match} И embedding IS NOT NULL
        for node in self._estimates.fetch_matchable_nodes(estimate_id):
            try:
                result = self._matcher.match_one(node.embedding, node.embedding_input)
            except TransientError:                       # сеть/429/таймаут
                if self._can_retry():                    # Celery retries не исчерпаны
                    raise                                # → autoretry задачи, идемпотентный резюм
                result = NodeMatch(ERROR, match_error="...")  # исчерпаны → фиксируем error, не валим смету
            self._estimates.save_node_match(node.id, result)  # перезаписывает весь снимок, match_error→NULL на успехе
        # 4) агрегат
        errors = self._estimates.count_node_errors(estimate_id)        # строго WHERE status='error'
        unfinished = self._estimates.count_unfinished_nodes(estimate_id)  # status='pending' (вектор не записался)
        if errors or unfinished:
            self._estimates.set_status(estimate_id, PARTIAL_ERROR,
                                       detail=f"errors={errors} unfinished={unfinished}")
        else:
            self._estimates.set_status(estimate_id, READY)
    finally:
        self._estimates.release_matching_lock(estimate_id)
```

**Завершимость embed-цикла** (три смыкающихся предохранителя — бесконечный цикл невозможен):
1. `fetch_unembedded_nodes(after_id=...)` — keyset-курсор по `id`: один проход возрастающими
   id, тот же узел не возвращается дважды в рамках задачи.
2. `embed_batch` — строгий контракт: возвращает **ровно** `len(input)` векторов в порядке
   входа, иначе исключение; на стыке — `zip(strict=True)`.
3. `fetch_matchable_nodes` фильтрует `embedding IS NOT NULL`: узел, которому вектор молча
   не записался (CAS-`False`/рассинхрон), остаётся `pending` без вектора и **не** попадёт в
   `match_one(None, …)`; его доберёт следующий ре-триггер.

## Ядро `match_one(embedding, query_text)` (рефактор `MatchingService`)

Не ре-эмбеддит — вектор приходит готовым (сохранён в `estimate_rows.embedding`):

```python
def match_one(self, embedding: list[float], query_text: str) -> NodeMatch:
    candidates = self._repo.search_similar(embedding, top_k=self._top_k)   # по готовому вектору
    if not candidates:
        return NodeMatch(NO_MATCH, score=None, candidates=[])
    best = candidates[0]
    if best.score > self._threshold:                                       # score = similarity (1 - cosine_distance)
        return NodeMatch(CONFIDENT, best.article.id, best.article.article_code,
                         best.article.name, best.score, candidates)
    chosen = self._llm.choose_best(query_text, candidates)                 # query_text = embedding_input узла
    if chosen is None:                                                     # арбитр отказался → НЕ найдено
        return NodeMatch(NO_MATCH, score=None, candidates=candidates)      # candidates сохраняем для SP3
    return NodeMatch(NEEDS_REVIEW, chosen.id, chosen.article_code, chosen.name,
                     score_of(chosen, candidates), candidates)             # score = косинус ВЫБРАННОГО
```

- `score` — это **similarity** (выше = лучше, `1 - cosine_distance`), порог `0.90`
  читается однозначно. Хранится копией (иммутабельный исторический факт).
- При `needs_review`, где LLM взял не top-1, `score` ниже косинуса top-1 — это норма
  (отражает реально выбранную статью). SP3 для «насколько хорош был лучший кандидат»
  читает `candidates[0].score`, а не `score`. Оба сигнала сохранены.
- Улучшение vs старого кода: LLM-отказ → `no_match` (а не `needs_review` с `matched=None`).
  Поэтому `needs_review` всегда означает «есть выбранный кандидат» — упрощает SP3.
- `match_row(EstimateRow)`/`match_rows` удаляются вместе со старым путём.

## Модель данных (миграция `0004`)

Только `ADD COLUMN … NULL`, без backfill. `0004` после `0003`.

**`estimate_rows` — снимок матчинга (все nullable, иммутабельны после записи):**

| Колонка | Тип | Смысл |
|---|---|---|
| `matched_article_id` | `INTEGER NULL` (**plain, без FK**) | мягкая ссылка на статью. SERIAL не переиспользуется → висячий id безопасен; `LEFT JOIN` к живой статье работает без FK; FK-каскад стёр бы аудит, RESTRICT запретил бы wipe справочника — оба противопоказаны |
| `matched_code` | `VARCHAR(64) NULL` | замороженная копия `article_code` |
| `matched_name` | `TEXT NULL` | замороженная копия имени |
| `score` | `DOUBLE PRECISION NULL` | честный similarity выбранного кандидата; `no_match → NULL` |
| `candidates` | `JSONB NULL` | топ-K снимок `[{id, code, name, score}]` (с `id` — SP3 перелинкует по id) |
| `match_error` | `TEXT NULL` | краткая причина при `status='error'`; на успехе перезаписывается в `NULL` |

`estimate_rows.status` уже `VARCHAR(32)` (0003) — держит `needs_review`(12)/`no_match`(8).

**`estimates`:**

| Колонка | Тип | Смысл |
|---|---|---|
| `status_detail` | `TEXT NULL` | причина `blocked` / сводка `partial_error` / «восстановление после обрыва» |

`estimates.status` уже `VARCHAR(32)` (0003) — держит `partial_error`(13).

**Доменные енумы (слаги для хранения):**
- `EstimateRowStatus`: `pending / confident / needs_review / no_match / error`.
- `EstimateStatus`: `pending / running / ready / partial_error / blocked`.
- Рус. подписи → маппинг в API-DTO/UI, **не** в БД. Рус. `MatchStatus` ретайрится из домена.

## Стейт-машины

**Estimate** (`estimates.status`):

| from | событие | to |
|---|---|---|
| — | ingest (SP1) | `pending` |
| pending / blocked / partial_error / running | `match_estimate` взял try-lock | `running` (коммит до embed; если был `running` → detail «восстановление после обрыва») |
| running | gate: `total==0` или `pending>0` | `blocked` (+detail) |
| running | обработка завершена, errors>0 ИЛИ остались `pending`-узлы без вектора | `partial_error` (+detail) |
| running | все узлы терминальны (errors==0, unfinished==0) | `ready` (может содержать no_match/needs_review) |
| running | крах воркера (PG отпустил лок при обрыве) | остаётся `running` → восстановление ре-триггером |
| partial_error | успешный ре-матч, все `error`-строки доведены без `error` | `ready` |
| partial_error | устойчивый транзиент на `error`-строках | остаётся `partial_error` — **терминально до SP3-ревью** |

**Row** (`estimate_rows.status`):

| from | событие | to | пишет (`save_node_match` перезаписывает весь набор) |
|---|---|---|---|
| — | ingest | `pending` | embedding=NULL |
| pending | embed-шаг | `pending` | embedding (статус не меняется) |
| pending/error/no_match | best.score>порога | `confident` | matched_* + score(best) + candidates; `match_error→NULL` |
| pending/error/no_match | best≤порога, LLM выбрал | `needs_review` | matched_*(выбранный) + score(выбранного) + candidates; `match_error→NULL` |
| pending/error/no_match | 0 кандидатов | `no_match` | score=NULL, candidates=[]; `match_error→NULL` (перезапись пустого снимка допустима) |
| pending/error/no_match | LLM отказался | `no_match` | score=NULL, candidates=топ-K (для SP3); `match_error→NULL` |
| pending/error/no_match | транзиент после ретраев | `error` | `match_error` заполнен |
| confident / needs_review | ре-триггер | без изменений | **иммутабельны** (решения, возможно тронутые в SP3) |

Ре-триггер перематчивает `{pending, error, no_match}` (пустые/несделанные снимки),
защищает `{confident, needs_review}` (осмысленные решения).

## Конкурентность

- **`pg_try_advisory_lock(classid, objid)`** — **неблокирующий**: на prefork
  concurrency>1 второй экземпляр `match_estimate(id)` сразу `no-op` (не висит, не
  занимает воркер-процесс). `classid` = namespace-константа «estimate matching»,
  `objid` = `estimate_id` (двухаргументная форма — иначе `estimate_id=42` столкнулся бы
  с любым другим местом, взявшим одноаргументный лок на 42).
- Лок берётся/отпускается на **одном пиннутом коннекте**, release в `finally`.
- **Session-level** (не `xact`-level): `xact`-лок отпустился бы на первом из
  инкрементальных коммитов embed-шага.
- **Лок как детектор живости:** упал воркер → коннект отвалился → Postgres сам отпустил
  лок → ре-триггер из `running` дозабирает работу; жив и пишет → лок держится → второй
  `no-op`. Статус `running` — пользовательский lifecycle, не замок; крах не «залочивает»
  навсегда.

## Ретраи и ошибки

- Транзиентные сбои (сеть/429/таймаут) при embed/LLM → проброс → **Celery autoretry +
  экспоненциальный backoff** (конечное число попыток). Идемпотентный резюм: embed-шаг
  пропускает заэмбедженное (keyset-курсор + CAS), match-шаг — терминальные кроме
  `no_match`. Пока ретраи не исчерпаны — задача перезапускается целиком (а не валит узел).
- **Исчерпание ретраев** (retry-count-aware: `self.request.retries >= max_retries`) →
  затронутый узел фиксируется `error` (+ `match_error`), цикл продолжается на остальных,
  смета → `partial_error`. Один устойчиво-плохой узел не валит смету и не зацикливает её.
  `error`-узлы доберёт следующий ре-триггер (matchable включает `error`).
- `count_node_errors` считает **строго `WHERE status='error'`** (не по `match_error`), а
  `save_node_match` на успехе перезаписывает `match_error → NULL` — иначе ре-матч
  `partial_error` дал бы залипший статус (стейл `match_error`).

## API

- **`POST /api/estimates/{id}/match`** — ре-триггер матчинга. Ставит `match_estimate(id)`,
  **разрешён из `{pending, blocked, partial_error, running}`** (в т.ч. `running` — это
  закрывает «воркер умер посреди матча» политикой ре-триггера, без реапера). Владение
  как в SP1 (owner-or-admin; чужая/нет → 404). Идемпотентность гарантирует, что повтор
  домётчивает только незавершённое.
- **`POST /api/articles/embed`** — админский (require_admin). Ставит `embed_articles()`.
  Замена ручному `just embed-worker`.
- Снимается **`POST /estimates/match`** (синхронный stateless-матч). Реальный поток теперь
  — upload (SP1) → авто-enqueue `match_estimate` + ре-триггер по требованию.

**Проводка триггеров:** `EstimateService.ingest` (SP1) получает зависимость `TaskQueue`
и в конце успешного ingest зовёт `enqueue_match(estimate_id)`; пути импорта/добавления
справочника зовут `enqueue_articles_embed()`.

## Снятие старого пути

| Удаляем/рефакторим | Действие | Проверка |
|---|---|---|
| `POST /estimates/match` + его DTO (`MatchResultOut` и т.п.) | удалить | grep консьюмеров; фронт на моках (CLAUDE.md) |
| `ExcelEstimateParser` + `EstimateRow` | удалить | нет др. вызовов |
| `MatchingService.match_row/match_rows` | удалить, оставить ядро `match_one` | старые тесты → на `match_one` |
| `MatchStatus` (рус.) | ретайр из домена → слаги + display-map в DTO | подтверждено: рус. статусы **нигде не хранились** (старый поток stateless; `estimate_rows.status` создан в 0003 слагом `pending`) |
| `just embed-worker` + `embed_worker.py` | снять команду/скрипт; логику `embedding_worker` обернуть в задачу `embed_articles` | тесты воркера переезжают |
| `deps.py` старая проводка | перепровод на ядро + новые сервисы/таск-кью | импорт-смоук |

## Конфигурация и эксплуатация

- `backend/.env`: `CELERY_BROKER_URL` (или `REDIS_URL`) — managed Redis на Timeweb;
  секреты не коммитим. Result backend **не задаётся**.
- `Settings` (`core/config.py`): поля брокера.
- `justfile`: рецепт запуска воркера (dev `--pool=solo`); снятие `embed-worker`.
- Без Docker: Redis удалённый, Celery-воркер — обычный python-процесс через `uv run`.

## Тесты

- Чистые сервисы (`match_one`, `match_estimate`, embed-логика) — фейками портов
  (`ArticleRepository`/`Embedder`/`LLMMatcher`/`EstimateRepository`/`TaskQueue`), без
  реальных БД/Redis/AI.
- Celery-обёртки — `task_always_eager=True` либо прямой вызов нижележащего сервиса.
- Фейк `TaskQueue` (записывает enqueue-вызовы) для тестов `EstimateService.ingest` и
  путей справочника.
- Покрыть: идемпотентность embed (повторный прогон не дублирует), gate (пустой/неполный
  справочник → blocked), все переходы Row (включая LLM-отказ→no_match, ре-матч
  no_match→confident, иммутабельность confident/needs_review), `count_node_errors` по
  статусу, обнуление `match_error` на успехе, advisory-lock дедуп (фейк-лок),
  стейл-`running` → detail «восстановление».

## Безопасность миграции / стык с SP1

- `0004` — только `ADD COLUMN … NULL` + plain-int `matched_article_id` (без FK, без
  backfill). Отгруженные SP1-строки остаются `pending` (и row, и estimate) — это и есть
  «ждёт матчинга»; новые слаг-енумы **включают `pending`**, значения валидны.
- Рус. `MatchStatus` нигде не персистился (см. таблицу снятия) — ретайр енума не оставляет
  в БД нечитаемых значений.
- `VARCHAR(32)` держит все новые статусы.

## Ключевые решения и обоснования

1. **Celery + Redis (managed Timeweb), без result backend.** Postgres — источник правды;
   задачи fire-and-forget. Redis удалённый → «без Docker» не нарушается.
2. **`TaskQueue`-порт над Celery, методы → `None`.** Домен/сервисы не знают о Celery;
   абстракция не течёт (никто не завязан на task-id).
3. **Две задачи, не три.** Эмбеддинг узлов — под-операция внутри `match_estimate`
   (идемпотентная), а не отдельная enqueue-able задача → нет двойного эмбеддинга.
4. **Матчинг требует полной готовности обоих эмбеддингов.** Частичный справочник →
   неверный top-K → врущий score. Gate: `total>0 AND pending==0`.
5. **`blocked` + ручной ре-триггер** (не авто-резюм) при неготовом справочнике.
6. **Снимок иммутабелен; ре-матч только `{pending, error, no_match}`.** `confident/
   needs_review` — решения, защищены; `no_match` — пустой снимок, перезапись допустима.
7. **Честный score = similarity выбранного кандидата.** LLM выбирает кандидата, не меняет
   число; `no_match→NULL`. SP3 читает `candidates[0].score` для «качества top-1».
8. **`matched_article_id` — plain-int без FK.** Полная иммутабельность снимка; SERIAL не
   переиспользуется; каскад/RESTRICT противопоказаны.
9. **Неблокирующий session-level 2-арг advisory-lock** как взаимоисключение + детектор
   живости; статус `running` — lifecycle, не замок.
10. **Завершимость embed-цикла** гарантирована keyset-курсором + строгим `embed_batch` +
    фильтром `embedding IS NOT NULL` в matchable.
11. **`match_error` обнуляется на успехе; `count_node_errors` по `status='error'`** — иначе
    залипший `partial_error` при ре-матче.
