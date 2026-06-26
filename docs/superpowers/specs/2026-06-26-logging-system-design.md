# Дизайн: система логирования (backend CIW)

**Дата:** 2026-06-26
**Статус:** утверждён к реализации
**Scope:** backend (FastAPI-веб + Celery-воркер + CLI-скрипты). Фронтенд не затрагивается.

## Проблема

Централизованного логирования нет. Работает дефолтный root-logger Python (только
WARNING+ в stderr, формат по умолчанию). Ad-hoc `logging.getLogger(__name__)` есть лишь
в паре AI-адаптеров (`openrouter_*`, `llm_matching_common`); в скриптах — `print()`.
Нет корреляции запросов/задач и наблюдаемости за AI-пайплайном (всё происходит «втихомолку»).

## Цели (все три — один связный фундамент)

1. **Фундамент:** единый формат, уровни, ротация, покрытие всех трёх классов процессов.
2. **Дебаг инцидентов:** сквозная корреляция `request_id → task_id` через web и Celery.
3. **Наблюдаемость пайплайна:** провайдер / латентность / попытки на AI-вызовах,
   per-estimate summary матчинга.

## Подход

Stdlib `logging`, человекочитаемый текст — по устоявшемуся паттерну соседнего проекта UDP
(`backend/logging_config.py`): централизованный `setup_logging()`, консоль + ротируемые файлы,
`LOG_LEVEL` из env, усмирение шумных библиотек, по модулю `getLogger(__name__)`.

**Почему не structlog/loguru:** ноль зависимостей логирования в `pyproject.toml`; для объёма
«консоль + файлы» +1 к дереву не окупается; Windows-боль (cp1252) ни тот ни другой не упрощают;
наблюдаемость закрывается `extra={...}` поверх существующих адаптеров. Путь к JSON позже —
замена одного форматтера, без правки кода логирования.

**Конфиг — императивный `setup_logging()`** (не `dictConfig`): совпадение с UDP важнее;
выгода dictConfig (общий словарь для uvicorn `--log-config`) обнуляется приёмом clear+propagate.

---

## Секция 1 — Модуль `logging_config` (фундамент)

**Файл:** `backend/app/core/logging_config.py` (рядом с `config.py`; cross-cutting, без доменных
зависимостей).

`setup_logging()` — по паттерну UDP, идемпотентный:

- **Хендлеры:** консоль (`StreamHandler`, уровень = `LOG_LEVEL`); `logs/app.log`
  (`RotatingFileHandler`, DEBUG, 10 МБ × 5, `encoding="utf-8"`); `logs/errors.log`
  (WARNING, `encoding="utf-8"`).
- **Формат:**
  `%(asctime)s | %(levelname)-7s | %(name)-25s | req=%(request_id)s task=%(task_id)s | %(message)s`
- **`os.makedirs(LOG_DIR, exist_ok=True)` ДО создания файловых хендлеров** — иначе первый
  запуск без `logs/` падает `FileNotFoundError`.
- **Идемпотентность:** модульный флаг `_configured` + `root.handlers.clear()` — защита от
  дублей при `uvicorn --reload` и повторных импортах.
- **`LOG_LEVEL` из `os.getenv`, НЕ из `Settings`** — намеренно. `Settings` требует валидных
  `DATABASE_URL`/`JWT_SECRET`; логирование не должно от этого зависеть (скрипты/воркер
  настраивают логи до и независимо от полной валидации конфига). Также env-флаги:
  `LOG_TO_FILE` (default `1`; `0` → только консоль, для прод-агрегатора), `LOG_DIR`
  (default `backend/logs`).
- **Усмирение шумных либ:** `httpx`, `httpcore`, `urllib3`, `botocore`, `s3transfer` → WARNING.
- **Хендофф uvicorn:** очистить хендлеры `uvicorn` / `uvicorn.access` / `uvicorn.error` +
  `propagate=True`, чтобы их записи шли через наш root (иначе дубли поверх наших).
  Порядок гарантирован: uvicorn конфигурит логирование в `Config.load()` **до** импорта
  приложения → наш `setup_logging()` в `create_app()` отрабатывает вторым и выигрывает.
  `--log-config` не нужен.

## Секция 2 — Сквозная корреляция web → Celery (ключевая)

**Контекст** (в `logging_config.py` либо `core/log_context.py`):

- Два `ContextVar`: `request_id_var`, `task_id_var`; хелперы `get/bind/reset`.
- `RequestIdFilter(logging.Filter)` — на **каждом** хендлере; всегда проставляет
  `record.request_id` / `record.task_id`, дефолт `-` (иначе формат падает на записях без
  атрибута: логи старта, внутренний uvicorn).

**FastAPI** (`app/api/middleware.py`):

- **Чистый ASGI-middleware** (не `BaseHTTPMiddleware` — у него проблемы с видимостью contextvar
  в эндпоинте). Читает входящий `X-Request-ID` или генерит `uuid4().hex[:8]`, ставит
  `request_id_var` в той же корутине, кладёт `X-Request-ID` в ответ. Логирует старт/финиш:
  метод, путь, статус, `duration_ms`.
- **Санитайз входящего `X-Request-ID`** (клиентский, идёт прямо в строку лога): обрезать длину
  (64) + выкинуть CR/LF/control-символы (log-injection). **Если после вычистки строка
  схлопнулась в пустую — фоллбэк на `uuid4`** (пустой id дальше не несём).

**Проброс web → Celery** (`CeleryTaskQueue`):

- `enqueue_match`: `match_estimate_task.delay(id)` → `match_estimate_task.apply_async((id,),
  headers={"request_id": get_request_id()})` — id запроса едет в заголовке сообщения.

**Celery-воркер:**

- `@setup_logging.connect` → зовёт наш `setup_logging()`; `worker_hijack_root_logger=False` в
  `celery_app.conf` — иначе Celery переопределит конфигурацию и форматтер/фильтр молча не
  применятся.
- `@task_prerun.connect`: ставит `task_id_var = task.request.id` и `request_id_var` из заголовка.
  `@task_postrun.connect`: **обязательно сбрасывает оба** — на solo-pool (Windows-дефолт)
  процесс переиспользуется; без сброса id протекут в следующую задачу.
- **OPEN ITEM (тихий отказ):** точный аксессор заголовка в воркере
  (`task.request.get("request_id")` vs `task.request.headers[...]`) версионно-зависим в
  celery 5.6.3. **Прибить одним прогоном через реальный Redis** (НЕ eager). Отказ тихий —
  `request_id` просто останется `-` в воркере, ничего не упадёт.

## Секция 3 — Точки наблюдения за пайплайном

**`EstimateMatchingService.match_estimate`** ([estimate_matching_service.py:44](../../../backend/app/services/estimate_matching_service.py#L44)):
обернуть таймингом; в конце один INFO-summary: `estimate_id`, всего узлов, исключено (ORG →
`EXCLUDED`), сматчено по статусам (`confident / needs_review / no_match / error` — точно по
`EstimateRowStatus`), `duration_ms`. Постадийно — DEBUG: «classify done (n)», «embed done (n)»,
«match done».

**AI-адаптеры — инструментация в AI-слое, НЕ в `retry.py`.** `retry_transient` — generic-хелпер
(опаковая `fn` + `classify`, возвращает только результат); провайдера/модели не видит и зовётся
из четырёх адаптеров. Класть туда `extra={provider, model}` = layering violation. Provider/model
живут в адаптере (`self._model`, провайдер = класс), который оборачивает весь `retry_transient(...)`
— это и есть граница «одного логического вызова».

- **Generic-хук в `retry_transient`:** добавить опциональный
  `on_retry: Callable[[int, Exception], None] | None = None`.
  **Placement — строго внутри гварда `if attempt < budget - 1:`** (семантика «ретрай
  запланирован»). Тогда `on_retry_count == attempts - 1` на **обоих** путях (успех-после-ретраев
  и исчерпание бюджета), и наблюдатель считает `attempts = count + 1` без ветвления по исходу.
  Вызов в except-теле до гварда дал бы off-by-one (на исчерпании count == attempts, на успехе
  count == attempts−1).
- **AI-хелпер `infrastructure/ai/_instrumented.py`:** `instrumented_call(provider, model, fn)` —
  таймер вокруг `retry_transient(...)`, считает попытки через `on_retry`-замыкание, пишет
  summary с `extra={"provider", "model", "latency_ms", "attempts", "outcome"}`. Ключи
  неймспейснуты — без зарезервированных (`name`, `message`, `args`), иначе
  `KeyError: Attempt to overwrite`. Адаптер зовёт `retry_transient` через этот хелпер.
- **Логирование на ВСЕХ путях** (`try/finally`, не только после успешного `return`):
  `outcome ∈ {ok, transient_exhausted, error}`. Перманентная ошибка → `classify=False` →
  `retry_transient` ре-рейзит сразу (`on_retry` ни разу не вызван); исчерпание → `TransientError`.
  На отказах уровень поднять до WARNING/ERROR, после лога — ре-рейз. Иначе наблюдаемость нулевая
  ровно когда нужнее.
- **Гранулярность (зафиксировано явно):** арбитр (`openrouter_matcher` / `anthropic_matcher`) →
  1 INFO **на вызов**; классификатор → 1 INFO **на батч** (`classifier_batch_size=40`); эмбеддер
  → 1 INFO на батч. Иначе `latency_ms` / `attempts` нечитаемы.

Существующие `logger.warning` / `logger.error` в адаптерах остаются.

## Секция 4 — Интеграция в точки входа

- **Web:** `setup_logging()` в начале `create_app()` (под флагом идемпотентности); регистрация
  `RequestIdMiddleware`.
- **Celery:** через сигналы (Секция 2).
- **Скрипты** (`create_admin`, `smoke_import`, `embed_worker`): `setup_logging()` в начале.
  **Правило замены `print`:** диагностика → `logger`; фактический результат программы → оставить
  `print`. Конкретно: `smoke_import.py: print(report)` — это вывод скрипта (отчёт в stdout),
  **остаётся `print`**; `create_admin` — статусные строки, → `logger`.

## Секция 5 — Windows / utf-8 + безопасность файлов

- **Кириллица в консоли (cp1252 → `UnicodeEncodeError`):** в `setup_logging()` —
  `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` в `try/except` (поток может быть
  не `TextIOWrapper`). `errors="replace"` — страховка: при тихом провале reconfigure
  некодируемый символ выродится в плейсхолдер, а не уйдёт в `handleError`-шум. Файлы и так
  `encoding="utf-8"`.
- **`RotatingFileHandler` не multiprocess-safe:** на solo (Windows-dev) ок. На prod-prefork
  `--concurrency>1` несколько процессов гонят ротацию по одному файлу → гонка/порча. Решение:
  `LOG_TO_FILE=0` на проде (лог в stdout, ротация снаружи — systemd/journald). Зафиксировано
  здесь и в `.env.example`.

## Секция 6 — Тесты и сопутствующее

**Тесты** (pytest, без реальной БД/AI — по [tests/fakes.py](../../../backend/tests/fakes.py)):

- `setup_logging()` идемпотентен (двойной вызов → нет дублей хендлеров).
- `RequestIdFilter` ставит дефолт `-` на записи без контекста.
- Middleware: `X-Request-ID` в ответе; непустой входящий — переиспользуется; вход из одних
  control-символов → фоллбэк на сгенерированный.
- Celery: `task_postrun` сбрасывает оба contextvar (защита от протечки на solo).
- `instrumented_call`: `attempts` корректен (успех-после-ретраев и исчерпание); summary пишется
  на путях `ok / transient_exhausted / error`.
- `extra`-поля не роняют запись.
- **web→Celery корреляция — ИНТЕГРАЦИОННЫЙ тест на реальном брокере, НЕ eager.**
  `task_always_eager` сериализует заголовок иначе, чем доставка через Redis, и пропустит тихую
  дыру из Секции 2 (аксессор заголовка). Минимум — ассерт аксессора на настоящем сообщении.

**Прочее:**

- `backend/logs/` в `.gitignore`.
- `LOG_LEVEL` / `LOG_TO_FILE` / `LOG_DIR` в `.env.example`.
- Короткая заметка в `docs/TECH_DEBT.md`: prod-файлы под prefork (`LOG_TO_FILE=0` + внешняя
  ротация) и возможный переход на JSON-форматтер при появлении агрегатора.

---

## Новые / изменяемые файлы (карта)

| Файл | Действие |
|---|---|
| `backend/app/core/logging_config.py` | новый: `setup_logging()`, формат, хендлеры, contextvars, `RequestIdFilter` |
| `backend/app/api/middleware.py` | новый: ASGI `RequestIdMiddleware` |
| `backend/app/infrastructure/ai/_instrumented.py` | новый: `instrumented_call(provider, model, fn)` |
| `backend/app/infrastructure/retry.py` | + generic-хук `on_retry` (placement в гварде) |
| `backend/app/infrastructure/tasks/celery_app.py` | + сигналы `setup_logging`/`task_prerun`/`task_postrun`, `worker_hijack_root_logger=False` |
| `backend/app/infrastructure/tasks/task_queue.py` | `enqueue_match` → `apply_async(headers=...)` |
| `backend/app/main.py` | `setup_logging()` + регистрация middleware |
| `backend/app/services/estimate_matching_service.py` | per-estimate summary + постадийный DEBUG |
| AI-адаптеры (matcher×2, embedder, classifier) | вызов `retry_transient` через `instrumented_call` |
| `backend/app/scripts/{create_admin,smoke_import,embed_worker}.py` | `setup_logging()`; `print`→`logger` по правилу |
| `backend/.env.example`, `.gitignore`, `docs/TECH_DEBT.md` | конфиг-флаги, `logs/`, заметка |

## Открытые вопросы / риски

1. **Аксессор заголовка в Celery 5.6.3** (Секция 2) — линчпин, отказ тихий. Прибивается одним
   прогоном через реальный Redis на этапе реализации.
2. **Файлы на проде под prefork** — отложено в TECH_DEBT (`LOG_TO_FILE=0` + внешняя ротация).
