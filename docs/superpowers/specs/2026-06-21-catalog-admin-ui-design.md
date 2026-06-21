# Catalog Admin UI — Design

**Дата:** 2026-06-21
**Статус:** черновик на ревью

## Проблема

Бэкенд умеет загружать справочник СМР (`POST /api/articles/import`, эндпоинты статей,
auth с ролями), но фронтенд — изолированный мок-прототип: логин фейковый
(`src/lib/mock/auth.ts`), реального API-клиента нет, JWT не используется, роль `admin`
в UI не существует. Страница «Справочник» ([ArticlesPage.tsx](../../../frontend/src/pages/ArticlesPage.tsx))
рендерит `MOCK_ARTICLES` с уже удалённым полем `section_name` — это и есть «шум».
В результате админ физически не может загрузить шаблон в систему.

## Цель

Вертикальный слайс: подключить фронтенд к реальному бэкенду в части **аутентификации** и
**справочника**, дать админу загрузить шаблон (с превью), добавлять статьи по одной, удалять
по одной и полностью очищать справочник. Поток смет (`pages/estimate/`) остаётся на моках —
вне этого слайса.

## Скоуп

**В скоупе:**
- Бэкенд: новый admin-роут `DELETE /api/articles` (полная очистка справочника).
- Фронтенд: реальный API-клиент, реальный auth (JWT), переписанная страница справочника,
  поток загрузки шаблона (превью→подтверждение), ручное добавление/удаление статьи, полная очистка.

**Вне скоупа:**
- Поток смет (загрузка/матчинг) — остаётся на моках, не трогаем `pages/estimate/`.
- Регистрация пользователей из UI (бэкенд `POST /api/auth/users` есть, но в слайс не входит).
- Сворачиваемое дерево, серверная пагинация, IndexedDB.

## Бэкенд: полная очистка справочника

Новый эндпоинт в направлении Clean Architecture (порт → сервис → роут):

- **Порт** `ArticleRepository.delete_all() -> int` (возвращает число удалённых строк).
- **SQL-реализация** в [article_repository.py](../../../backend/app/infrastructure/db/article_repository.py):
  `delete(TemplateArticleModel)` без `where`, `commit`, вернуть `result.rowcount`.
  `ON DELETE CASCADE` по `parent_id` корректно сносит дерево.
- **Сервис** `ArticleService.delete_all() -> int` — тонкая делегация в репозиторий.
- **Роут** `DELETE /api/articles` (`dependencies=[Depends(require_admin)]`), `200`,
  тело `{"deleted": <int>}`. Гард удаления (`requires_force`) НЕ применяется — это явная
  админская операция «очистить всё».
- **Фейк** `FakeRepository.delete_all()` — `n = len(self._store); self._store = []; return n`.
- **Тесты:** unit на сервис (delete_all чистит и возвращает счётчик); тест роута
  (admin → 200 + счётчик; не-admin → 403; через `dependency_overrides` + `FakeRepository`).

DTO ответа: `DeleteAllResponse {deleted: int}` в `schemas.py`.

## Фронтенд: архитектура

Новые модули (каждый — одна ответственность, тестируется изолированно):

- `src/lib/api/client.ts` — fetch-обёртка. База `/api` (vite-прокси → :8260). Подставляет
  `Authorization: Bearer <token>` из провайдера токена. Парсит JSON; на не-2xx бросает
  `ApiError {status: number, message: string}` (вытягивает `detail` если строка, иначе
  `detail.message`, иначе текст статуса). Отдельный метод для multipart (без `Content-Type`,
  чтобы браузер выставил boundary).
- `src/lib/api/auth.ts` — `login(email, password): Promise<string>` (POST `/auth/login` →
  `access_token`); `me(): Promise<AuthUser>` (GET `/auth/me`).
- `src/lib/api/articles.ts` — `listArticles(): Promise<Article[]>`; `createArticle(input):
  Promise<Article>`; `deleteArticle(id): Promise<void>`; `deleteAllArticles(): Promise<number>`;
  `importTemplate(file, {dryRun, force}): Promise<ImportReport>`.
- `src/lib/auth/AuthContext.tsx` — React-контекст `{user, role, loading, login, logout}`.
  Токен в `sessionStorage` (`ciw.auth.token`): переживает перезагрузку вкладки, очищается при
  закрытии, не шарится между вкладками. (Не localStorage — по решению: не персистить вечно.)
  `client.ts` читает токен из `sessionStorage` напрямую (единый источник правды, без циклической
  зависимости с контекстом); `AuthContext` пишет/чистит тот же ключ. На `401` `client.ts` зовёт
  зарегистрированный контекстом колбэк `onUnauthorized` для logout.

**Типы** (`src/lib/types.ts`, под DTO бэкенда):
```ts
export interface Article { id: number; article_code: string; name: string; parent_id: number | null }
export interface AuthUser { id: number; email: string; role: "user" | "admin"; is_active: boolean }
export interface ImportReport {
  created: number; updated: number; deleted: number; unchanged: number
  skipped: string[]; pending_embeddings: number; dry_run: boolean; force_required: boolean
}
```
Существующий `Candidate` (с `section_name`) используется estimate-моками — НЕ трогаем.

## Фронтенд: аутентификация

- `LoginScreen` → `auth.login(email, password)` → токен в `sessionStorage` → `auth.me()` →
  заполняем `user`/`role` в контексте. Ошибка → «Неверный логин или пароль».
- `AuthContext` при монтировании: если токен есть — `me()` для валидации (протух/401 → logout,
  чистый токен). Пока идёт проверка — `loading`.
- `AuthGate` — пока `loading` показывает спиннер/пусто; затем `LoginScreen` либо приложение.
- `AppShell` — показывает email + роль; «Выйти» → `logout()` (чистит токен + контекст) +
  `clearReview()`.
- **401 от любого запроса** → `client.ts` инициирует logout (через колбэк, заданный контекстом).
- Удаляем `src/lib/mock/auth.ts`.

## Фронтенд: страница справочника

`listArticles()` (бэкенд отдаёт до 1000, отсортировано по коду численно) → плоская таблица:
- Колонки: **Код** (моноширинный, отступ слева по глубине = `article_code.split(".").length - 1`),
  **Наименование**, действие удаления (только admin).
- Сверху — клиентский поиск (input), фильтрует по подстроке в коде ИЛИ имени (регистронезависимо).
- Состояния: загрузка (скелет/«Загрузка…»), ошибка (текст + кнопка «Повторить»), пусто
  («Справочник пуст — загрузите шаблон»).

**Гейтинг роли:**
- Не-admin: только список + поиск (read-only).
- Admin дополнительно:
  - Секция «Загрузить шаблон» (см. ниже).
  - Форма ручного добавления одной статьи: поля `article_code`, `name`, `parent_code?`
    (`POST /api/articles`); 400/409 → текст ошибки рядом с формой; успех → рефреш списка.
  - Кнопка удаления в строке (`DELETE /api/articles/{id}`) с подтверждением.
  - Кнопка «Очистить справочник» (`DELETE /api/articles`) с подтверждением вводом
    (ввести слово, напр. «УДАЛИТЬ», чтобы активировать) → успех → рефреш + сообщение «Удалено N».

## Фронтенд: поток загрузки шаблона (превью → подтверждение, только admin)

1. Выбор `.xlsx` (`<input type="file">`).
2. `importTemplate(file, {dryRun: true})` → показываем отчёт-превью: создано/обновлено/удалено/
   без изменений/`pending_embeddings`; список `skipped` (если есть, сворачиваемый).
3. Если `force_required` — заметное предупреждение: «Импорт удалит N строк (снос корня/>20%).
   Подтвердите принудительный импорт».
4. Кнопка «Применить» → `importTemplate(file, {dryRun: false, force: report.force_required})`
   → финальный отчёт + рефреш списка. Файл хранится в state между шагами.
5. На `409` (если состояние разошлось между превью и применением) — тот же диалог force
   (`detail.message`/`detail.deleted` уже в `ApiError`).
6. `400` (невалидный файл/структура) → текст ошибки, превью не строится.

## Обработка ошибок

`ApiError {status, message}` единообразно:
- `401` → авто-logout (токен протух/невалиден).
- `400`/`409` → показываем `message` бэкенда (дубликат, узел-предок, невалидный файл, force).
- Сетевые/`5xx` → общий тост/сообщение «Не удалось выполнить запрос, попробуйте ещё».
- Никаких «тихих» проглатываний — все ветки видимы пользователю.

## Тестирование (vitest + RTL)

Мокаем модуль `src/lib/api/*` (или `fetch`). Покрываем:
- **AuthContext:** login сохраняет токен в sessionStorage и заполняет user/role; logout чистит;
  стартовая валидация по `me()`; 401 разлогинивает.
- **ArticlesPage:** рендер списка с отступом по глубине; фильтр по коду/имени; admin-действия
  скрыты у не-admin; состояния загрузки/ошибки/пусто.
- **Поток загрузки:** превью (dry_run) → подтверждение (dry_run=false); ветка `force_required`
  (предупреждение + force в применении); отображение `skipped`.
- **Полная очистка:** кнопка активна только после ввода слова-подтверждения; вызывает
  `deleteAllArticles`; рефреш.
- Бэкенд: unit-тесты `delete_all` (сервис) + роут (`200`/`403`).

## Критерии готовности

- Админ логинится реальным аккаунтом, видит справочник из БД (без `section_name`-шума),
  загружает `Шаблон.xlsx` через превью→подтверждение, добавляет/удаляет статьи, очищает справочник.
- Не-admin видит только read-only список.
- Все тесты (бэк pytest + фронт vitest) зелёные; ruff + eslint чисты.
- Поток смет не затронут.
