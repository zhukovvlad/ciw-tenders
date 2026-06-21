# 2026-06-22 — Catalog Admin UI: реальный auth + справочник СМР из БД

## Что сделано

Фронтенд подключён к реальному бэкенду в части аутентификации и справочника СМР: реальный
JWT-логин вместо мока, просмотр справочника из БД, admin-операции (загрузка шаблона с превью,
ручное добавление статьи, полная очистка). На бэке добавлен один admin-роут `DELETE /api/articles`.
Поток смет (`pages/estimate/`) остаётся на моках.

Спек: [docs/superpowers/specs/2026-06-21-catalog-admin-ui-design.md](../superpowers/specs/2026-06-21-catalog-admin-ui-design.md).
План: [docs/superpowers/plans/2026-06-21-catalog-admin-ui.md](../superpowers/plans/2026-06-21-catalog-admin-ui.md).
PR: [#4](https://github.com/zhukovvlad/ciw-tenders/pull/4) (база `main`).

### Бэкенд

- `DELETE /api/articles` (admin, `require_admin`) → `200 {"deleted": int}` — полная очистка справочника.
  Через все слои Clean Architecture: порт `ArticleRepository.delete_all` ([ports.py](../../backend/app/domain/ports.py))
  → SQL-адаптер (`delete()` + `rowcount`, [article_repository.py](../../backend/app/infrastructure/db/article_repository.py))
  → `ArticleService.delete_all` → DTO `DeleteAllResponse` → роут (зарегистрирован **до** `DELETE /{article_id}`,
  иначе path-param проглотит пустой путь). Схема БД/ORM не менялись.

### Фронтенд

- **API-слой** `src/lib/api/`: `client.ts` — единый `ApiError`, Bearer-токен из `sessionStorage`
  (ключ `ciw.auth.token`), колбэк `onUnauthorized`, multipart-загрузка; единственный читатель токена
  из стораджа. Модули `auth` (`login`/`me`) и `articles` (`listArticles`/`createArticle`/`deleteArticle`/
  `deleteAllArticles`/`importTemplate`).
- **Аутентификация** — `lib/auth/AuthContext` (JWT в `sessionStorage`, **не** localStorage); хук `useAuth`
  вынесен в `lib/auth/useAuth.ts`. Старт: `401 → logout`, `5xx`/сеть → токен сохранён + ошибка.
  `LoginScreen`/`AuthGate`/`AppShell` переведены на контекст, мок `lib/mock/auth.ts` удалён.
- **Справочник** (`pages/ArticlesPage` + `components/articles/*`): `ArticleTable` (отступ по глубине кода +
  клиентский поиск), `ManualAddForm` (admin, 400/409), `TemplateUpload` (dry-run превью → согласие на
  `force` → применение, обработка 409-дрейфа), `WipeCatalog` (подтверждение вводом слова `УДАЛИТЬ`).
  Состояния loading/error/empty, роль-гейтинг (косметика поверх серверного `require_admin`).

## Верификация (выполнена)

- Фронт: `npm run typecheck` (`tsc -b`) чисто; `npm run lint` (eslint) 0 ошибок; `prettier --check` чисто;
  `npx vitest run` → **21 файл / 74 теста** зелёные.
- Бэк: `uv run pytest` → **80 passed**; `uv run ruff check .` чисто.
- Миграция `0002` (add `embedding_input`) накатана на прод-БД (`ep-green-bar`) при смоук-прогоне —
  до этого база была на `0001`, листинг/импорт падали с `UndefinedColumn`.

## Решения и нюансы

- **Авторизация только серверная** (`require_admin`); клиентский роль-гейтинг — косметика.
- **401-carve-out:** `client.ts` зовёт `onUnauthorized` (разлогин) на 401 **кроме** `/auth/login` —
  неверный логин не выкидывает из сессии, а протухший токен на любом другом роуте выкидывает.
- **`reloadKey`-паттерн** в `ArticlesPage` (счётчик в эффекте) вместо `await reload()` — чтобы не
  нарушать `react-hooks/set-state-in-effect`; колбэки `onCreated/onApplied/onWiped` фаер-энд-форгет.
- **`useAuth` в отдельном файле** — `react-refresh/only-export-components` не даёт экспортировать хук
  рядом с компонентом-провайдером. `loading` в `AuthContext` инициализируется лениво от наличия токена
  (убрали синхронный `setState` в эффекте).
- **`ApiError` — обычное поле, не parameter property:** `tsconfig.app.json` включает `erasableSyntaxOnly`
  (TS1294 на `public status`).
- **Гейт был дырявым (поймано при смоуке):** `npm run typecheck` запускал `tsc --noEmit` на корневом
  solution-`tsconfig.json` (`files: []` + `references`) → не проверял ничего. Исправлено на `tsc -b --noEmit`.
  Prettier не входил в гейт (eslint его не дублирует) — добавлен `prettier --check` в `just lint`, а
  `.gitattributes` форсит LF (перекрывает `core.autocrlf=true`, согласовано с `.prettierrc endOfLine: lf`).
- Процесс: брейншторм → спек → план (2 раунда ревью) → subagent-driven реализация (10 задач, ревью
  спек-соответствия + качества после каждой + финальное ревью всей ветки на Opus; модель под сложность).
  Ревью поймало реальный Important (вводящий в заблуждение `await reload()`) и кросс-тасковую регрессию
  `App.test.tsx` (тест на исчезнувший мок-заголовок). AI-ревью PR (CodeRabbit) — валидные nitpick'и
  пофикшены (type=button, aria-label, reload чистит actionError, login чистит токен при сбое `me()`,
  re-entry guards, строгий assert).

## Осталось / TODO

- **Эмбеддинги справочника:** после импорта строки висят с `embedding=NULL` — нужно прогнать
  `just embed-worker --once` (для RAG-матчинга). Воркер пока ручной — оформлено как тех-долг
  ([TECH_DEBT.md](../TECH_DEBT.md): авто-старт по расписанию или по событию обновления таблицы).
- **Отложенная полировка** (не блокеры, из финального ревью): тест non-401 ветки `LoginScreen`;
  гонка `onPick` в `TemplateUpload` (AbortController); alias-свип `@/` в тестах.
- **403 обрабатывается обобщённо** (сознательное отступление от спеки): общий `catch` показывает
  сообщение бэка без logout; для одиночного админа 403 из UI почти недостижим.
