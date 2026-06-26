# 2026-06-26 — Централизованное логирование backend + сквозная корреляция

## Что сделано

Своя система логирования на stdlib `logging` (без structlog/loguru) поверх всех трёх классов
процессов бэкенда (FastAPI-web, Celery-воркер, CLI-скрипты): единый формат, уровни на хендлерах,
ротация файлов, **сквозная корреляция `request_id → task_id`** через web и Celery, и точки
наблюдения за AI-пайплайном (провайдер/латентность/попытки на вызов, per-estimate summary матчинга).

Три связанные цели одного фундамента: (1) единый формат/уровни/ротация на всех входах;
(2) дебаг инцидентов — корреляция запроса через web→Celery; (3) наблюдаемость пайплайна.

Спек: [docs/superpowers/specs/2026-06-26-logging-system-design.md](../superpowers/specs/2026-06-26-logging-system-design.md).
План: [docs/superpowers/plans/2026-06-26-logging-system.md](../superpowers/plans/2026-06-26-logging-system.md).
Ветка `feat/logging-system` (база `main`), смерджена через **PR #13** (`abe57d7`). Код-коммиты
`0db1fed..d072821` (13: 8 задач + 2 фикс-петли ревью + проба-до커м Celery + полировка + фикс CodeRabbit).

## Архитектура

`api → services → domain ← infrastructure`. Логирование — cross-cutting инфра в `app/core/`,
**без доменных зависимостей**; конфиг из `os.getenv`, НЕ из `Settings` (логи не должны зависеть от
валидации `DATABASE_URL`/`JWT_SECRET` — скрипты/воркер настраивают логи до неё).

- **core:** [logging_config.py](../../backend/app/core/logging_config.py) — `setup_logging()` (консоль
  на stdout + ротируемые `logs/app.log` DEBUG / `logs/errors.log` WARNING; `root=DEBUG` как пол,
  per-sink фильтрация уровнями хендлеров; идемпотентно), `ContextVar`-ы request_id/task_id +
  `RequestIdFilter` (стоит на каждой записи, дефолт `-`), хелперы `bind_*`/`reset_correlation`.
- **api:** [middleware.py](../../backend/app/api/middleware.py) — чистый ASGI `RequestIdMiddleware`
  (НЕ `BaseHTTPMiddleware` — у того проблемы с видимостью contextvar в эндпоинте): санитайз/генерация
  `X-Request-ID`, заголовок в ответе, лог запроса, сброс в `finally`. Регистрируется в `create_app`
  ПОСЛЕ CORS → внешний слой.
- **infrastructure/ai:** [_instrumented.py](../../backend/app/infrastructure/ai/_instrumented.py) —
  `instrumented_call` (таймер + попытки + один summary на любом исходе; ре-рейз load-bearing).
- **infrastructure/tasks:** [celery_app.py](../../backend/app/infrastructure/tasks/celery_app.py) —
  сигналы `setup_logging`/`task_prerun`/`task_postrun` + `worker_hijack_root_logger=False`;
  [task_queue.py](../../backend/app/infrastructure/tasks/task_queue.py) — `enqueue_match` пробрасывает
  request_id в заголовке `apply_async`.

## Бэкенд (8 задач, строгий TDD)

- **Task 1 — ядро.** `setup_logging()` + контекст корреляции. `root.setLevel(DEBUG)` обязателен (иначе
  дефолтный WARNING срежет INFO/DEBUG до хендлеров — тихая дыра); per-sink фильтрация на уровнях
  хендлеров. Усмирение шумных либ (httpx/httpcore/…→WARNING), хендофф uvicorn (clear+propagate).
- **Task 2 — хук `on_retry`** в `retry_transient`: опциональный, зовётся строго в гварде
  `attempt < budget-1` → число вызовов `== fn-calls-1` на обоих путях (наблюдатель честно считает
  attempts без ветвления по исходу). Дефолт `None` — обратная совместимость.
- **Task 3 — `instrumented_call`:** обёртка вокруг `retry_transient`, считает попытки через
  `on_retry`-замыкание, пишет summary в `finally` на всех путях (`ok` INFO / `transient_exhausted`,
  `error` WARNING) с `extra={provider,model,latency_ms,attempts,outcome}`. Ре-рейз обязателен.
- **Task 4 — `RequestIdMiddleware`** + интеграция в `create_app`. Санитайз входящего id (control-символы
  прочь, ≤64; пусто после вычистки → uuid4). `setup_logging()` первой строкой `create_app()`.
- **Task 5 — корреляция Celery.** Сигналы: `task_prerun` биндит task_id + request_id из заголовка,
  `task_postrun` **сбрасывает оба** (solo-pool переиспользует процесс → иначе id протекут).
- **Task 6 — инструментация 4 AI-адаптеров** (openrouter embedder/matcher/classifier, anthropic matcher):
  вызов через `instrumented_call` вместо голого `retry_transient`. Фолбэк классификатора `→ UNSURE`
  сохранён (ре-рейз `instrumented_call` его не ломает).
- **Task 7 — per-estimate summary** в `EstimateMatchingService`: INFO с разбивкой по статусам
  (`Counter[EstimateRowStatus]`) + латентность + постадийный DEBUG. Поведение матчинга не изменено.
- **Task 8 — скрипты:** `setup_logging()` в точках входа; `create_admin` статус → `logger`,
  `smoke_import` `print(report)` остаётся (вывод программы, не диагностика).

## Открытый item: аксессор заголовка Celery 5.6.3 — закрыт пробой на реальном Redis

Спек §2 фиксировала линчпин-риск с тихим отказом: точный аксессор кастомного заголовка в воркере
версионно-зависим, а `task_always_eager` сериализует заголовок иначе доставки через Redis. **Проба
прогнана на живом брокере** (НЕ eager, НЕ юнит), на выделенной очереди `probe_q`, чтобы не дренить
чужие задачи общего брокера. Результат: `getattr(task.request, "request_id")` несёт переданный через
`apply_async(headers=...)` id, а строка трейса показала `req=<id>` сквозь всю задачу. Аксессор
**подтверждён эмпирически, не угадан** (коммит `d4dde7f` обновил комментарий в коде).

## Верификация

- Бэк: `PYTHONIOENCODING=utf-8 uv run pytest -q` → **263 passed, 3 skipped**; `uv run ruff check .`
  чисто. Юнит-тесты не ходят в сеть/БД/AI — фейки портов + `caplog` + стаб httpx-клиента.
- Процесс: subagent-driven (свежий субагент на задачу, независимое ревью spec+quality после каждой,
  фикс-петля по Critical/Important) → финальное whole-branch ревью (opus): **Ready to merge = Yes,
  0 Critical, 0 Important**. Все 4 нагруженных инварианта проверены сквозь задачи: (1) `root=DEBUG`
  доходит до app.log; (2) цепочка корреляции web→header→celery→filter→reset когерентна; (3) ре-рейз
  `instrumented_call` → фолбэк классификатора `UNSURE` цел; (4) все `extra`-ключи неймспейснуты.
- **Ручной web-smoke на реальном uvicorn** (не TestClient): `/health` отдаёт сгенерированный 8-символьный
  id и переиспользует входящий `X-Request-ID`; в `app.log` строки `uvicorn.access` **и** `app.request`
  штампованы `req=<id>` (хендофф uvicorn работает, contextvar виден его логгеру); `errors.log` создан и
  пуст (разделение по WARNING корректно).

## Код-ревью PR #13 (CodeRabbit)

- **✅ Исправлено (`d072821`): консольный `StreamHandler` писал в stderr**, тогда как код
  `reconfigure`-ит stdout под utf-8 → страховка от cp1252 (кириллица в Windows-консоли, спек §5) не
  покрывала реальный поток хендлера. Привязали хендлер к `sys.stdout`.
- **🔵 Оставлено по решению заказчика: `LOG_TO_FILE` дефолт `1`** (CodeRabbit рейтил Major). Это
  осознанный выбор дизайна: дев-окружение (solo-pool, без prefork, без Docker) получает файлы логов;
  `LOG_TO_FILE=0` уже задокументирован как прод-prefork-эскейп в `.env.example` и `TECH_DEBT`. Флип на
  `0` оставил бы дев без логов по умолчанию. Рационал отписан в треде PR.
- **Вне области:** 4 находки CodeRabbit по докам eval-харнесса (`matching-eval-harness*`) попали в
  диапазон PR из-за отстававшего `origin/main`. Вынесены отдельным комментарием в PR для будущего
  агента eval-харнесса — в этом PR не правились.
- Пропущено осознанно: docstring-coverage 80% — не конвенция проекта.

## Решения и нюансы

- **stdlib, не structlog/loguru.** Ноль зависимостей логирования; для объёма «консоль + файлы» +1 к
  дереву не окупается. Путь к JSON позже — замена одного форматтера, без правки кода логирования.
- **Императивный `setup_logging()`, не `dictConfig`** — совпадение с паттерном соседнего проекта важнее.
- **`enqueue_articles_embed` намеренно ВНЕ request-корреляции** (`.delay()`, без заголовка): fan-in drain
  тянет pending-статьи из многих запросов разом — один `request_id` на нём семантически размыт.
  Коррелируется только по task_id. Асимметрия осознанная, не баг.
- **`extra={...}` — только неймспейснутые ключи**, никогда зарезервированные (`name`/`message`/`args`)
  → иначе `KeyError: Attempt to overwrite`.

## Долг / на будущее (в [TECH_DEBT](../TECH_DEBT.md))

- 🟡 **Логи на проде под Celery prefork** (`--concurrency>1`): `RotatingFileHandler` не multiprocess-safe
  → гонка/порча файла. Решение: `LOG_TO_FILE=0` (stdout, ротация снаружи — systemd/journald). При
  появлении агрегатора (Loki/ELK) — JSON-форматтер вместо текстового (код логирования не трогается).

## Дальше

Документация синхронизирована: раздел «Логирование (backend)» в [CLAUDE.md](../../CLAUDE.md), операционная
заметка в [backend/README.md](../../backend/README.md). При появлении лог-агрегатора — переход на
JSON-форматтер; возможный авто-`embed-worker` и параллельный арбитр (отдельный долг) добавят свои точки
наблюдения поверх готового фундамента.
