# 2026-06-23 — SP2: асинхронный матчинг смет (Celery) + честный score

## Что сделано

Второй под-проект модуля `estimates`. Узлы сметы, лежащие после SP1 в статусе `pending`,
теперь **асинхронно** эмбеддятся и сопоставляются со справочником СМР через Celery+Redis.
По каждому узлу пишется иммутабельный снимок статьи (`matched_*`, `candidates`) и **честный
`score`** (косинус выбранного кандидата, не top-1), ведутся статусы строки и сметы. Один воркер
обслуживает и матчинг смет, и эмбеддинг справочника. Postgres — источник правды (Celery result
backend не используется). Старый синхронный путь `POST /api/estimates/match` снят.

Спек: [docs/superpowers/specs/2026-06-23-estimate-matching-sp2-design.md](../superpowers/specs/2026-06-23-estimate-matching-sp2-design.md).
План: [docs/superpowers/plans/2026-06-23-estimate-matching-sp2.md](../superpowers/plans/2026-06-23-estimate-matching-sp2.md).
PR: _(заполнить)_ (база `main`). Коммиты `27bd258..HEAD` (12 задач).

## Архитектура

`api → services → domain ← infrastructure`. Порт `TaskQueue` над Celery; Celery-приложение/задачи
в `infrastructure/tasks/`; чистые сервисы (`MatchingService.match_one`,
`EstimateMatchingService.match_estimate`) зависят только от портов. Транзиент гасится инлайн в
адаптерах; неготовность справочника (gate) — bounded retry в тонкой Celery-обёртке через доменный
`DictionaryNotReadyError`.

## Бэкенд

- **Конфиг (Task 1):** `celery_broker_url`, тайм-лимиты задачи (`task_soft/time_limit_s`),
  per-call AI-таймаут + бюджет транзиента, knobs gate-retry. Зависимость `celery[redis]` (через `uv add`).
- **Миграция `0004` + ORM (Task 2):** снимок на `estimate_rows` (`matched_article_id` — plain INTEGER
  без FK для иммутабельности снимка; `matched_code/name`, `score`, `candidates` JSONB, `match_error`)
  + `estimates.status_detail`. Накатывается на прод человеком (`just migrate`); тесты проверяют только метаданные ORM.
- **Домен (Task 3):** статусы `EstimateRowStatus` / `EstimateStatus` (StrEnum-слаги), снимок `NodeMatch` /
  `MatchCandidate` / `MatchableNode`; ошибки `TransientError`, `DictionaryNotReadyError(total, pending)`.
- **Ядро матчинга (Task 4):** `MatchingService.match_one(embedding, query_text)` — без ре-эмбеддинга
  (смета хранит вектор). `score>0.90` ⇒ confident (top-1); иначе LLM-арбитр ⇒ needs_review со счётом
  **выбранного** кандидата; отказ/галлюцинация (выбор вне кандидатов) ⇒ no_match со снимком кандидатов.
- **Порты + фейки (Task 5):** `TaskQueue`; `ArticleRepository.matching_readiness`; методы
  `EstimateRepository` (advisory-lock, статус/heartbeat, keyset-эмбеддинг, CAS, matchable-фильтр, снимок, счётчики).
- **Оркестрация (Task 6):** `EstimateMatchingService.match_estimate` — `embed → gate → match → статус`
  под локом, heartbeat'ы; `mark_blocked` под локом не затирает терминальный статус. Чист от Celery.
- **SQL-адаптеры (Task 7):** session-level 2-арг advisory-lock (`pg_try_advisory_lock`), keyset-эмбеддинг,
  CAS по `embedding_input`, перезапись всего снимка, счётчики. Интеграц-тест эксклюзивности лока на
  реальном Postgres (gated `RUN_LOCK_INTEGRATION`, в CI — SKIPPED).
- **Транзиент в адаптерах (Task 8):** `retry_transient` (бюджет + бэкофф) + hard-timeout; сеть/429/5xx →
  `TransientError`; структурный брак LLM (не-JSON / выбор вне кандидатов) → `None` (отказ, без ретрая).
- **Celery (Task 9):** приложение (broker=Redis, без result backend), задачи `match_estimate_task` /
  `embed_articles_task`, `CeleryTaskQueue`, singleton-лок справочного эмбеддинга + drain-to-zero.
  Gate-неготовность → `self.retry`; исчерпан бюджет → `mark_blocked`.
- **DI + enqueue (Task 10):** проводка `TaskQueue`/matching-service; `ingest` энкьюит матчинг **после
  коммита** create, best-effort (падение брокера не валит загрузку — смета остаётся `pending`).
- **API (Task 11):** `POST /api/estimates/{id}/match` (202, проверка владения, честный `detail` при
  `running`), `POST /api/articles/embed` (admin) + enqueue в импорте/создании справочника (не на dry-run);
  снимок матчинга в DTO; снят `POST /api/estimates/match`.
- **Чистка (Task 12):** удалены `excel_parser.py`, старый `embed_worker.py`, `MatchStatus`/`EstimateRow`/
  `MatchResult`/`MatchResultOut`, старые DI-фабрики; рецепт `just celery-worker` (solo-pool для Windows).

## Критичный инвариант: пиннутый коннект под advisory-lock

Session-level advisory-lock переживает `COMMIT` только на **одном** backend-коннекте. Поэтому каждая
Celery-задача держит `conn = engine.connect()` на всё время и строит `SessionLocal(bind=conn)` — при
внешнем bind `commit()` НЕ возвращает коннект в пул, лок остаётся эксклюзивным (важно на
`prefork concurrency>1`). `release_*_lock` → `session.close()` → `conn.close()` в finally;
краш/SIGKILL рвёт коннект → Postgres сам отпускает лок (детектор живости). Финальное ревью
подтвердило корректность на всех путях выхода.

## Верификация (выполнена)

- Бэк: `PYTHONIOENCODING=utf-8 uv run pytest` → **140 passed, 1 skipped** (lock-integration gated),
  9 warnings (библиотечные, тест-окружение); `uv run ruff check .` чисто.
- Тесты не ходят в реальную БД/Redis/MinIO/AI — фейки портов + `dependency_overrides`; Celery-обёртки
  тестируются через чистую `run_match` (без брокера).
- Миграция `0004` накатывается на прод-БД человеком (`just migrate`) перед мерджем.

## Решения и нюансы

- **Честный `score`** = косинус ВЫБРАННОГО арбитром кандидата; выбор вне топ-K трактуется как отказ.
- **Иммутабельность снимка:** ре-матч трогает только `{pending, error, no_match}` (matchable-фильтр);
  `confident`/`needs_review` неприкосновенны. В `partial_error` сметy толкают только `error`/`unfinished`,
  но не `no_match`/`needs_review`.
- **Gate-retry:** матчинг не стартует, пока справочник не заэмбежен полностью (`pending==0` и `total>0`);
  эмбеддинг узлов всё равно выполняется (не впустую), затем bounded ожидание → при исчерпании `blocked`.
- **Процесс:** план с реальным кодом на каждый шаг → subagent-driven реализация (свежий субагент на
  задачу, независимое ревью spec+quality после каждой, фиксы под локом) → финальное whole-branch ревью.
  Поймано и исправлено по ходу: баг в тест-хелпере (`emb or [0.1]` глотал `None`); неверный gate
  интеграц-теста (conftest задаёт фейковый postgres URL → `skipif` по `DATABASE_URL` не срабатывал);
  dry-run-импорт энкьюил лишний эмбеддинг. Отклонён ложноположительный отзыв ревьюера про
  `SessionLocal(bind=conn)` (проверено: SA 2.0.51 принимает `bind`).

## Долг / на будущее (вынесено в [TECH_DEBT](../TECH_DEBT.md))

- Статус `running` не самовосстанавливается после жёсткого краша воркера (лок Postgres отпускает,
  но строку никто не перепишет; ре-триггер при этом работает) → SP3 staleness-sweep / проверка живости лока.
- Узкий перехват исключений в embed/match-циклах (только `TransientError`): непредвиденный
  не-транзиентный сбой может оставить смету в `running` → расширить except / wrapper-level → `partial_error`.
- Пул коннектов vs concurrency воркера при выходе за `--pool=solo`; drain на каждый `create_article`.

## Дальше

SP3 — ревью/правки совпадений + запись `Статья СМР` обратно в файл + выгрузка `.xlsx`. Зависит от SP2.
