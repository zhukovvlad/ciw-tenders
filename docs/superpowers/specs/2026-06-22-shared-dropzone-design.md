# Дизайн: общий компонент Dropzone + загрузка шаблона на drag-and-drop

**Дата:** 2026-06-22
**Статус:** согласован, ждёт ревью спеки
**Ветка:** продолжение `feat/shadcn-migration` (ещё не влита; та же UI-полировка)

## Проблема

Загрузка шаблона справочника (`TemplateUpload`) использует голый `<input type="file">` —
пользователю не нравится эта форма. При этом в потоке смет (`StartScreen`) уже есть
аккуратная нативная drag-and-drop дропзона («Перетащите смету или выберите файл», иконка,
hot-состояние, скрытый input), стилизованная под токены CIW. То есть нужный drag-and-drop
UX в проекте уже реализован — но как одноразовая вёрстка внутри `StartScreen`, не
переиспользуемая.

Цель: вынести этот паттерн в общий компонент `Dropzone` и применить его и в `TemplateUpload`
(вместо голого input), и в `StartScreen` (вместо инлайн-вёрстки). Без новых зависимостей.

## Решения (согласовано)

- Общий **нативный** компонент (HTML5 drag-events + скрытый input), **без** react-dropzone и
  иных новых зависимостей.
- Применяем в обоих местах: `TemplateUpload` (справочник) и `StartScreen` (поток смет).
- Safety-флоу импорта шаблона (dry-run превью → подтверждение → force / 409-дрейф) **сохраняется
  без изменений** — меняется только способ выбора файла.

## Охват

- Создать: `frontend/src/components/Dropzone.tsx` (+ `Dropzone.test.tsx`).
- Изменить: `frontend/src/components/articles/TemplateUpload.tsx` (+ его тест — минимально).
- Изменить: `frontend/src/pages/estimate/StartScreen.tsx` (поведение сохраняется; тесты
  `StartProcessing.test.tsx`, `EstimateFlow.test.tsx`, `App.test.tsx` остаются зелёными через
  `ariaLabel`).

**Вне охвата:** остальной estimate-поток, `lib/mock/`, `Candidate`, `MOCK_*`. Логика импорта
шаблона и API не меняются.

## Компонент `Dropzone`

Интерфейс:

```tsx
interface DropzoneProps {
  onFile: (file: File) => void
  accept: string          // атрибут input + источник списка допустимых расширений для drop
  id: string              // связь label/htmlFor + якорь для input
  ariaLabel: string       // доступное имя input (a11y + запросы в тестах)
  disabled?: boolean
  idleText?: string        // основной текст в покое
  hotText?: string         // текст при перетаскивании над зоной
  hint?: string            // подпись (моноширинная, как в StartScreen)
  className?: string       // переопределение размеров контейнера
}
```

Поведение (1-в-1 как текущий `StartScreen`):

- `onDragOver` → `preventDefault()` + `hot=true`; `onDragLeave` → `hot=false`.
- `onDrop` → `preventDefault()`, `hot=false`, взять `files[0]`; принять, только если расширение
  совпадает с одним из перечисленных в `accept` (иначе тихо игнорировать — как сейчас в
  `StartScreen`). Допустимые расширения выводятся из `accept` (разбор по запятой, токены `.xxx`).
- Клик по зоне открывает системный диалог: вся зона — `<label htmlFor={id}>`, внутри скрытый
  `sr-only` `<input id={id} type="file" accept={accept} aria-label={ariaLabel} onChange=…>`.
  В `onChange` — та же проверка расширения, затем `onFile(f)`.
- `disabled` → визуально приглушить, отключить обработчики/курсор.

Вид: иконка `UploadCloud` (`lucide-react`), токены CIW — `rounded-lg border border-dashed`,
hot → `border-primary` + `bg-[color-mix(in_srgb,var(--primary)_6%,transparent)]`,
idle → `border-[var(--ds-border-strong)]`, тексты `text-foreground` / `text-muted-foreground`,
`hint` моноширинный. Высота по умолчанию компактная; `StartScreen` передаёт `className`
с большей высотой (`min-h-64`), чтобы сохранить текущий крупный вид стартового экрана.

Проверка расширения — единый помощник внутри компонента (используется и в `onDrop`, и в
`onChange`), чтобы не дублировать regex.

## `TemplateUpload`

- Заменить блок `<Label htmlFor="tpl-file"> + <Input type="file">` на:
  ```tsx
  <Dropzone
    onFile={onPick}
    accept=".xlsx"
    id="tpl-file"
    ariaLabel="Файл шаблона"
    idleText="Перетащите .xlsx-шаблон или выберите файл"
    hint="XLSX-шаблон справочника"
    disabled={busy}
  />
  ```
- `onPick` меняет сигнатуру с `(e: React.ChangeEvent<HTMLInputElement>)` на `(f: File)`:
  тело (сброс `preview`/`consent`/`conflict`, затем dry-run `importTemplate(f, {dryRun:true})`)
  сохраняется, просто берёт `f` напрямую вместо `e.target.files?.[0]`.
- Добавить над блоком превью строку с именем выбранного файла (например
  `Файл: {file.name}`), чтобы было видно, что выбрано.
- Превью / `Collapsible` пропущенных / force-`Alert` + `Checkbox` / 409 / кнопка «Применить» —
  **без изменений**.

## `StartScreen`

Заменить инлайн-`<label>`-дропзону на:

```tsx
<Dropzone
  onFile={onFile}
  accept=".xlsx,.xls"
  id="estimate-file"
  ariaLabel="файл сметы"
  idleText="Перетащите смету или выберите файл"
  hotText="Отпустите файл сметы"
  hint=".xlsx · .xls — обрабатываются строки «Вид раздела = СМР»"
  className="min-h-64"
/>
```

Поведение и тексты сохраняются. Валидация `.xlsx?`/`.xls` обеспечивается выводом расширений из
`accept` внутри `Dropzone` (эквивалент текущему `/\.xlsx?$/i`).

## Тесты

- **`Dropzone.test.tsx`** (новый): (1) клик-загрузка — `userEvent.upload(getByLabelText(ariaLabel), file)`
  вызывает `onFile` с файлом; (2) drop — `fireEvent.drop(zone, { dataTransfer: { files:[file] } })`
  вызывает `onFile`; (3) drop файла с неподходящим расширением `onFile` не вызывает;
  (4) `disabled` блокирует выбор. Тесты проверяют реальное поведение, не вёрстку.
- **`TemplateUpload.test.tsx`:** хелпер `pick()` остаётся
  (`userEvent.upload(screen.getByLabelText(/файл шаблона/i), …)`) — `Dropzone` даёт input
  `aria-label="Файл шаблона"`, запрос резолвится. Остальные тесты (dry-run/force/409/смена файла)
  по сути без изменений.
- **`StartProcessing.test.tsx` / `EstimateFlow.test.tsx` / `App.test.tsx`:** остаются зелёными —
  `getByLabelText(/файл сметы/i)` резолвится через `ariaLabel="файл сметы"`.

## Критерии готовности

- `Dropzone` используется и в `TemplateUpload`, и в `StartScreen`; дублирующей вёрстки дропзоны
  в `StartScreen` не остаётся.
- Голого `<input type="file">` в `TemplateUpload`/`StartScreen` нет (input скрыт внутри `Dropzone`).
- Новых зависимостей не добавлено.
- Полный гейт зелёный: `npm run typecheck` + `npm run lint` + `npm run format:check` +
  `npm run test`. Логика импорта шаблона и поведение выбора файла в смете сохранены.
