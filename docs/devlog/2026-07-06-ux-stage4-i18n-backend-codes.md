# 2026-07-06 — Этап 4 UX PR-1: машинные коды ошибок бэкенда

**Ветка:** `feat/i18n-backend-error-codes` (от `feat/ux-stage4-i18n` — спека и план
этапа 4 едут в этом же PR).
**Спека:** [2026-07-06-ux-stage4-i18n-design.md](../superpowers/specs/2026-07-06-ux-stage4-i18n-design.md),
§3 (контракт кодов — таблица §3.4).
План: [2026-07-06-ux-stage4-i18n-backend-codes.md](../superpowers/plans/2026-07-06-ux-stage4-i18n-backend-codes.md)
(Tasks 1–7, subagent-driven TDD).
**Коммиты:** `14fad00..e317e4c` (6 коммитов реализации от базы `8878163`).

## Что сделано

Каждая пользовательская ошибка и статус матчинга теперь несёт стабильный машинный
код в теле ответа: `{"detail": <прежний русский текст>, "code": "<snake_case>"}`.
Код — семантика ситуации, живёт в доменном слое (атрибут исключения); фронт (PR-2)
резолвит его в локализованный текст ru/tr. Полный список из 37 кодов — контракт
[§3.4](../superpowers/specs/2026-07-06-ux-stage4-i18n-design.md) (здесь не дублируется).

- **Доменный слой** (§3.1). Введён базовый `DomainError(Exception)` с классовым
  `code: str` и переопределением аргументом конструктора (для многопричинных
  классов — `TemplateValidationError`, `InvalidReviewActionError`). Все 13
  существующих исключений переведены под него; добавлены `EstimateNotFoundError` /
  `EstimateRowNotFoundError`. `LookupError`-точки в трёх сервисах
  (`estimate_review`/`estimate_export`/`estimate_service`) заменены на них —
  `Grep LookupError backend/app` = 0.
- **API-слой** (§3.2). Новый `ApiError(HTTPException)` с полем `code` + общие
  хендлеры (`register_error_handlers`) рендерят единую форму тела. Голые
  `HTTPException`-литералы мигрированы (`Grep "HTTPException("` в `backend/app` = 0;
  осталось только наследование `class ApiError(HTTPException)`). Хендлер
  `RequestValidationError` (422) отдаёт `validation_error` + `errors` через
  `jsonable_encoder`. `AuthError`/`DuplicateError` — глобальные хендлеры (401 с
  `WWW-Authenticate: Bearer` сохранён); `account_disabled` — ctor-override в точке
  raise (иначе залоченный юзер получил бы дезинформирующий `invalid_credentials`).
- **Домены** (§3.4). auth (`deps`/`auth_service`), estimates/upload/review/
  completion/export (роут + сервисы), articles/import (роут + `article_service`/
  `template_parser`). 202-ответ перезапуска матчинга несёт `match_queued` /
  `match_already_running` / `match_requeued`.
- **Персистируемые статусы** (§3.3, серая зона). Миграция `0010` — nullable
  `estimates.status_code TEXT`; порт `set_status` получил `code`, протянут через
  репозиторий и фейки; 4 писателя (`matching_partial_error` / `matching_unexpected`
  / `matching_blocked_dictionary` / `matching_reset_after_crash`); `EstimateDetailOut`
  дополнен `status_code` (PR-2 читает его для локализованного баннера). `status_detail`
  не трогается — сырая диагностика (фолбэк при `status_code IS NULL`).

## Инвариант обратной совместимости

`detail` в каждом ответе остаётся прежним русским текстом байт-в-байт (включая
объектный `detail` DeletionGuard: ключи `message`/`force_required`/`deleted`);
`code` — строго добавка. Существующие тесты на тексты не правились, кроме двух
санкционированных точек (спека §3.5): `test_estimate_sweep.py` (2 ассерта текстов →
коды) и `test_import_endpoint.py` (форма DeletionGuard: `code` на верхнем уровне).
Правки `pytest.raises(LookupError)` → `EstimateNotFoundError` в
`test_estimate_completion.py` — следствие смены типа исключения (§3.1), не правка
текста. Фронт мигрирует на коды без флаг-дня.

## Процесс: subagent-driven TDD

Исполнители задач — Sonnet, ревью каждой задачи и финальный whole-branch ревью —
Opus. Каждая из 6 задач прошла индивидуальное ревью чисто (spec ✅ + quality
Approved, 0 Critical/Important). Финальный whole-branch ревью (Opus, 6 коммитов):
**Ready to merge — Yes**; подтверждено, что все 37 кодов имеют live raise-site и
наоборот (нет сирот), серии `matching_*`/`match_*` не скрещены (включая `_do_sweep`,
где оба встречаются в одном запросе), MRO хендлеров разрешается верно.

## Верификация

- `uv run pytest -q` — **442 passed, 3 skipped, 0 failed**. `uv run ruff check .` —
  чисто. Юнит-тесты на фейках портов (без реальной БД/AI) + real-Postgres
  интеграционные (`TEST_DATABASE_URL`).
- **Тест-БД и миграция `0010`.** Интеграционные fund-тесты
  (`test_estimate_repository_fund_integration.py`) сначала краснели: ORM получил
  `status_code`, а тест-БД была на `0009` → `UndefinedColumn` при запросе → отравлённая
  сессия → `finally`-очистка sentinel-юзера не отработала → остаточный dup-row маскировал
  корень `UniqueViolation`. Это ровно рецидив известного долга
  ([TECH_DEBT: «Тест-Postgres: миграции применяются вручную»](../TECH_DEBT.md)).
  Вылечено (с разрешения владельца): `DATABASE_URL=$TEST_DATABASE_URL alembic upgrade head`
  (тест-эндпоинт `ep-fragrant-frost`, отдельный от prod `ep-green-bar`; перед апгрейдом
  подтверждён резолв хоста) + удаление stale sentinel-строки. После — 442 зелёных.
- **Pre-existing ruff-format drift.** `ruff format --check .` краснит ~69 файлов
  репозитория, из них 18 тронуты этой веткой — но все 18 были «would reformat» уже на
  базе `7ffaa44` (проверено base-vs-head поштучно). Это репо-широкий долг форматирования,
  НЕ вклад этой ветки; переформатирование раздуло бы дифф шумом и смешало формат с фичей.
  Форс-гейт проекта — `ruff check` (зелёный); формат гоняется отдельно (`just fmt`).

## Вне скоупа / отложено

- **Prod-миграция `0010` — шаг владельца.** К облачной prod-БД (`DATABASE_URL`,
  `ep-green-bar`) миграция НЕ применялась — её катит владелец (`just migrate`) перед
  деплоем ветки. До применения ORM опережает схему prod (осознанно, дизайн плана §3.3:
  задача = файл ревизии + ORM + тест схемы).
- **PR-2 (фронтенд i18n)** — механика `i18next` + словари ru/tr + маппинг кодов —
  отдельный PR после мержа этого (спека §4). План PR-2 ещё не написан.
- Полировка (не блокеры, из финального ревью): `ErrorOut` — документационная модель,
  пока не подключена в `responses=` и не описывает поле `errors` 422-ответа (план:
  роуты подключат по мере надобности); `estimate_missing_columns` достаётся любому
  `ValueError` разбора (сегодня он один — watch-item, коммент в роуте).
