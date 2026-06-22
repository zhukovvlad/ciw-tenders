# Дизайн: перевод фронтенда на компоненты shadcn

**Дата:** 2026-06-22
**Статус:** согласован, ждёт ревью спеки

## Проблема

Фронтенд CIW использует shadcn/ui (стиль `radix-nova`, `radix-ui` + `shadcn` v4),
но из примитивов добавлены только 5: `badge`, `button`, `card`, `input`, `table`.
Остальной UI накручен вручную — голые `<button>` с ручными бордерами, `<label>`-обёртки,
`window.confirm`, сырые `<input type="file">` и `<input type="checkbox">`, повторяющиеся
inline-`<p className="text-destructive">`, `<details>`. Это рассинхронизирует внешний вид,
усложняет поддержку и доступность. Цель — поэтапно заменить кастом на штатные компоненты shadcn.

## Охват

В работе:

- `components/AppShell.tsx`
- `components/auth/LoginScreen.tsx`
- `pages/ArticlesPage.tsx`
- `components/articles/*` (`ArticleTable`, `ManualAddForm`, `TemplateUpload`, `WipeCatalog`)

**Вне охвата:** поток смет `pages/estimate/*` — сейчас на моках (`lib/mock/`), по
требованию CLAUDE.md не трогаем. `Candidate` / `MOCK_*` не затрагиваем.

## Решения (согласовано с пользователем)

1. **Порядок** — снизу вверх (вариант A): примитивы → AppShell → Card/Skeleton →
   AlertDialog → формы → TemplateUpload. Каждый этап = отдельный коммит/PR с зелёными
   `npm run typecheck` + `npm run lint` + `npm run test`.
2. **Формы** — полноценный shadcn `Form` + `react-hook-form` + `zod` + `@hookform/resolvers`.
3. **Отклик** — успех/ошибки действий через тосты `Sonner`; подтверждения опасных действий
   через `AlertDialog`.
4. **Очистка справочника** — ввод слова `УДАЛИТЬ` сохраняется, но переносится **внутрь**
   `AlertDialog`; кнопка подтверждения активна только при точном совпадении.
5. **Файловое поле** — у shadcn нет отдельного file-upload; используем `Input type="file"`
   (классы `file:*` уже есть в `input.tsx`).
6. **Список пропущенных строк** в импорте — переводим `<details>` на shadcn `Collapsible`.

## Принципы

- shadcn-компоненты в `src/components/ui/` — **вендорные, не править** (CLAUDE.md). Добавляем
  только через `npx shadcn add`.
- Кастомные токены `--ds-*` сохраняем — shadcn использует свои `--background/--foreground/
  --primary` и т.д., конфликта нет. Где уместно, заменяем `--ds-*` на семантические токены shadcn,
  но это не самоцель этапов.
- Импорты через alias `@/`. Иконки — `lucide-react`. TypeScript strict; `erasableSyntaxOnly`
  включён (без parameter properties/enum). Prettier `printWidth 80`, LF.
- Поведение каждого участка сохраняется (или явно улучшается); сначала тесты под новый UI, затем зелёный прогон.

## Этапы

### Этап 0 — фундамент (без изменения поведения)

- `npx shadcn add label checkbox alert tabs alert-dialog dropdown-menu sonner skeleton form collapsible`
- Зависимости: `react-hook-form`, `zod`, `@hookform/resolvers`, `sonner`.
- Смонтировать `<Toaster />` (sonner) в корне приложения (рядом с провайдерами темы/auth).
- Проверка: `typecheck` + `lint` + `test` зелёные, UI визуально не изменился.

### Этап 1 — AppShell

- Навигация (`<button>` + ручные `border-b-2`) → `Tabs` / `TabsList` / `TabsTrigger`
  с иконками `lucide-react` (`FileSpreadsheet`, `Library`). Управление вкладкой остаётся
  через проп `tab`/`onTab` (controlled).
- Блок «email · роль · Выйти» → `DropdownMenu`: триггер — почта; пункт с ролью disabled;
  пункт «Выйти» вызывает `clearReview()` + `logout()`.

### Этап 2 — каркас ArticlesPage

- Панели `rounded-md border` («Загрузить шаблон», «Добавить вручную», «Опасная зона») →
  `Card` (`CardHeader`/`CardTitle`/`CardContent`).
- Загрузка («Загрузка…») → `Skeleton` (строки-плейсхолдеры под таблицу).
- Ошибка загрузки справочника → `Alert` (variant `destructive`) + кнопка «Повторить».

### Этап 3 — подтверждения опасных действий

- Удаление статьи: `window.confirm` в `ArticlesPage.handleDelete` → `AlertDialog`
  (триггер — кнопка удаления в `ArticleTable`).
- `WipeCatalog`: поле ввода слова `УДАЛИТЬ` + кнопка переносятся внутрь `AlertDialog`;
  подтверждение активно только при `word === "УДАЛИТЬ"`.
- Результаты действий (удалено N, очищено N, ошибки) → тосты Sonner вместо inline-`<p>`.

### Этап 4 — формы на Form + RHF + zod

- `LoginScreen`: `Card` + `Form` (`FormField`/`FormItem`/`FormLabel`/`FormControl`/
  `FormMessage`). zod-схема: `email` непустой, `password` непустой. Ошибка сабмита
  (401 → «Неверный логин или пароль», прочее → «Не удалось войти…») — тост; при необходимости
  `FormMessage`/корневая ошибка.
- `ManualAddForm`: `Form` с zod-схемой (`article_code` обязателен, `name` обязателен,
  `parent_code` опционален → `null`). Успех — тост, форма сбрасывается.

### Этап 5 — TemplateUpload

- Сырой `<input type="file">` → `Input type="file"` + `Label`.
- Согласие на force (`<input type="checkbox">`) → `Checkbox` + `Label`.
- Предупреждение про force/деструктив → `Alert` (variant `destructive`).
- Список пропущенных строк (`<details>`) → `Collapsible` (`CollapsibleTrigger`/`CollapsibleContent`).
- Итог импорта (created/updated/...) → тост.

## Тесты

- RTL-тесты каждого этапа переписываются под новый UI: запросы через `getByRole`/labels shadcn,
  `window.confirm`-моки → взаимодействие с `AlertDialog`, проверки inline-ошибок → проверка тоста
  (мок `sonner`) или `FormMessage`.
- Файлы тестов: `LoginScreen.test`, `ManualAddForm.test`, `TemplateUpload.test`,
  `WipeCatalog.test`, `ArticleTable.test`, `ArticlesPage` (если есть).
- shadcn-компоненты не тестируем как таковые — проверяем поведение фич.

## Критерии готовности

- После каждого этапа: `npm run typecheck`, `npm run lint`, `npm run test` зелёные.
- Сырых `<button>`-навигаций, `window.confirm`, сырых `<input type="file"|"checkbox">`,
  `<details>` и ручных inline-`text-destructive` в охваченных файлах не остаётся.
- Поведение фич сохранено; estimate-поток не затронут.
