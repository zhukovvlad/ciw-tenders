# 2026-07-02 — Этап 1 UX-роадмапа: роутер и жизненный цикл сметы

**Ветка:** `feat/ux-stage1-router-lifecycle`
**Спека:** [../superpowers/specs/2026-07-02-ux-roadmap-design.md](../superpowers/specs/2026-07-02-ux-roadmap-design.md) (§3)
**План:** [../superpowers/plans/2026-07-02-ux-stage1-router-lifecycle.md](../superpowers/plans/2026-07-02-ux-stage1-router-lifecycle.md)

## Что сделано

Сметы стали URL-адресуемыми, фаза выводится из серверного состояния.

**Бэкенд:**
- `estimates.completed_at` (миграция `0008`) — оператор закрыл ревью; `None` = открыта.
- `PATCH /estimates/{id}/completion` `{"completed": bool}` → `{"completed_at": ...}`
  (владелец/админ; 409 для не-терминальных статусов). Завершённая смета read-only
  и на сервере: PATCH решения ревью → 409 (`EstimateCompletedError`), guard в
  `EstimateReviewService.apply()` до любых мутаций.
- Пагинация списка: `GET /estimates?limit=&offset=` + агрегаты прогресса ревью
  (`reviewed_count`/`total_reviewable`, FILTER-подзапрос, tie-breaker `id DESC`);
  партишн-тест громко ломается при добавлении нового статуса строки.

**Фронтенд:**
- react-router v7 (library mode): `/estimates`, `/estimates/:id`, `/articles`;
  логин-гейт поверх; табы AppShell — из `useLocation`.
- `EstimatePage` — единственный владелец маппинга статус→экран (спека §3):
  `pending|running` → прогресс+поллинг; `ready|partial_error` → ревью или итоговый
  (по `completed_at`); `blocked` → алерт с `status_detail` (в т.ч. при уходе в
  blocked во время поллинга — статус перечитывается).
- Кнопка «Завершить» (AlertDialog при нерешённых) и «Возобновить проверку».
- Список смет: колонка «Проверка» («X из Y» / бейдж «Завершена») и «Показать ещё».

## Ломающие изменения API

- `GET /estimates`: голый массив → `{"items": [...], "total": n}`.
- Новый `PATCH /estimates/{id}/completion`; `completed_at` в detail/summary DTO.

## Удалено

- sessionStorage-кэш ревью (`lib/session.ts`) и `beforeunload`-guard — источник
  истины теперь сервер, F5/прямая ссылка восстанавливают фазу честно.
- `EstimateFlow.tsx` (конечный автомат фаз) — заменён роутами.

## Верификация

`just lint` чист; бэк 383 passed / 3 skipped; фронт vitest 136/136, `tsc -b` 0,
prod-сборка ок. SQL-агрегаты сверены с живой dev-БД вручную (совпали точно,
`excluded` выпадает из `nodes_count`). Полный поток прогнан в браузере на живых
dev-серверах: загрузка → `/estimates/N` → поллинг → ревью → решение переживает
F5 → «Завершить» (диалог) → итоговый → F5 → вторая вкладка → «Возобновить» →
back → NotFound-алерт на несуществующем id.

Попутно вылечен schema drift тест-Postgres (остался на `0007` → интеграционные
тесты падали `UndefinedColumn`, маскируясь под `UniqueViolation` из-за
застрявшего sentinel-пользователя): применён `alembic upgrade head` на
`TEST_DATABASE_URL`, sentinel удалён.

## Сознательно вне объёма

Полировка из ревью (неотменяемый `pollEstimate`, `total` в `loadMore`, ассерт
дозагрузки) и ручные миграции тест-БД — заведено в
[TECH_DEBT](../TECH_DEBT.md#-этап-1-ux-роадмапа-полировка-из-ревью-не-блокирует)
(+ соседний пункт про `just migrate-test`).
