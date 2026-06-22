# Shared Dropzone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Вынести drag-and-drop дропзону в общий компонент `Dropzone` и применить его в `TemplateUpload` (вместо голого input) и `StartScreen` (вместо инлайн-вёрстки).

**Architecture:** Нативный компонент (HTML5 drag-события + скрытый `sr-only` input внутри `<label>`), без новых зависимостей, на базе текущего стиля `StartScreen`. Сначала создаём компонент с тестами, затем переводим на него два потребителя. Safety-флоу импорта шаблона (dry-run превью → подтверждение → force/409) не меняется.

**Tech Stack:** React 19, TypeScript (strict, erasableSyntaxOnly), Tailwind v4, shadcn-токены + `--ds-*`, lucide-react, vitest + React Testing Library.

## Global Constraints

- Работа только во `frontend/`. Никаких новых npm-зависимостей.
- Импорты через alias `@/`. Иконки — `lucide-react`. TypeScript strict; `erasableSyntaxOnly` (без parameter properties/enum).
- Prettier: `printWidth 80`, `endOfLine lf`. Перед коммитом — полный гейт: `npm run typecheck` + `npm run lint` + `npm run format:check` + `npm run test` (весь набор, не точечно).
- shadcn-компоненты в `src/components/ui/` — вендорные, не править. `Dropzone` — НЕ в `ui/` (это доменный компонент), кладём в `src/components/`.
- Вне охвата: остальной estimate-поток, `lib/mock/`, `Candidate`, `MOCK_*`. Логика импорта шаблона и API не меняются.
- Дропзона тихо игнорирует файл с неподходящим расширением при drop (поведение текущего `StartScreen`).

---

## File Structure

- **Create** `frontend/src/components/Dropzone.tsx` — переиспользуемая дропзона (одна ответственность: выбрать один файл через drag-drop/клик, отфильтровав по расширению).
- **Create** `frontend/src/components/Dropzone.test.tsx` — тесты компонента.
- **Modify** `frontend/src/components/articles/TemplateUpload.tsx` — заменить файловый input на `Dropzone`; `onPick` принимает `File`.
- **Modify** `frontend/src/components/articles/TemplateUpload.test.tsx` — минимальная правка (label → aria-label остаётся `/файл шаблона/i`).
- **Modify** `frontend/src/pages/estimate/StartScreen.tsx` — заменить инлайн-вёрстку на `Dropzone`.

(Тесты `StartProcessing.test.tsx`, `EstimateFlow.test.tsx`, `App.test.tsx` не меняются — `getByLabelText(/файл сметы/i)` резолвится через `ariaLabel`.)

---

## Task 1: Компонент Dropzone

**Files:**
- Create: `frontend/src/components/Dropzone.tsx`
- Test: `frontend/src/components/Dropzone.test.tsx`

**Interfaces:**
- Produces: `Dropzone` с пропсами
  `{ onFile: (file: File) => void; accept: string; id: string; ariaLabel: string; disabled?: boolean; idleText?: string; hotText?: string; hint?: string; className?: string }`.
  Вызывает `onFile(file)` только если имя файла оканчивается на одно из расширений из `accept`.

- [ ] **Step 1: Написать падающие тесты**

Создать `frontend/src/components/Dropzone.test.tsx`:
```tsx
import { describe, expect, it, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Dropzone } from "./Dropzone"

describe("Dropzone", () => {
  it("выбор файла через клик вызывает onFile", async () => {
    const onFile = vi.fn()
    render(<Dropzone onFile={onFile} accept=".xlsx" id="f" ariaLabel="файл" />)
    await userEvent.upload(
      screen.getByLabelText(/файл/i),
      new File(["x"], "doc.xlsx")
    )
    expect(onFile).toHaveBeenCalledTimes(1)
    expect(onFile.mock.calls[0][0].name).toBe("doc.xlsx")
  })

  it("drop файла вызывает onFile", () => {
    const onFile = vi.fn()
    render(<Dropzone onFile={onFile} accept=".xlsx" id="f" ariaLabel="файл" />)
    const zone = screen.getByText(/перетащите/i).closest("label")!
    fireEvent.drop(zone, {
      dataTransfer: { files: [new File(["x"], "doc.xlsx")] },
    })
    expect(onFile).toHaveBeenCalledTimes(1)
  })

  it("drop файла с неподходящим расширением игнорируется", () => {
    const onFile = vi.fn()
    render(<Dropzone onFile={onFile} accept=".xlsx" id="f" ariaLabel="файл" />)
    const zone = screen.getByText(/перетащите/i).closest("label")!
    fireEvent.drop(zone, {
      dataTransfer: { files: [new File(["x"], "doc.pdf")] },
    })
    expect(onFile).not.toHaveBeenCalled()
  })

  it("disabled блокирует выбор файла", async () => {
    const onFile = vi.fn()
    render(
      <Dropzone
        onFile={onFile}
        accept=".xlsx"
        id="f"
        ariaLabel="файл"
        disabled
      />
    )
    const input = screen.getByLabelText(/файл/i)
    expect(input).toBeDisabled()
    await userEvent.upload(input, new File(["x"], "doc.xlsx"))
    expect(onFile).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Прогнать — падает**

Run: `npx vitest run src/components/Dropzone.test.tsx`
Expected: FAIL (модуль `./Dropzone` не существует).

- [ ] **Step 3: Реализовать Dropzone**

Создать `frontend/src/components/Dropzone.tsx`:
```tsx
import { useState } from "react"
import { UploadCloud } from "lucide-react"
import { cn } from "@/lib/utils"

interface DropzoneProps {
  onFile: (file: File) => void
  accept: string
  id: string
  ariaLabel: string
  disabled?: boolean
  idleText?: string
  hotText?: string
  hint?: string
  className?: string
}

function matchesAccept(name: string, accept: string): boolean {
  const exts = accept
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter((s) => s.startsWith("."))
  if (exts.length === 0) return true
  const lower = name.toLowerCase()
  return exts.some((ext) => lower.endsWith(ext))
}

export function Dropzone({
  onFile,
  accept,
  id,
  ariaLabel,
  disabled = false,
  idleText = "Перетащите файл или выберите",
  hotText = "Отпустите файл",
  hint,
  className,
}: DropzoneProps) {
  const [hot, setHot] = useState(false)

  function take(file: File | undefined | null) {
    if (!file) return
    if (matchesAccept(file.name, accept)) onFile(file)
  }

  return (
    <label
      htmlFor={id}
      onDragOver={(e) => {
        if (disabled) return
        e.preventDefault()
        setHot(true)
      }}
      onDragLeave={() => setHot(false)}
      onDrop={(e) => {
        e.preventDefault()
        setHot(false)
        if (disabled) return
        take(e.dataTransfer.files?.[0])
      }}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border border-dashed p-6 text-center transition-colors",
        hot
          ? "border-primary bg-[color-mix(in_srgb,var(--primary)_6%,transparent)]"
          : "border-[var(--ds-border-strong)]",
        disabled && "cursor-not-allowed opacity-60",
        className
      )}
    >
      <UploadCloud className="size-7 text-muted-foreground" />
      <div className="text-foreground">{hot ? hotText : idleText}</div>
      {hint && (
        <div className="font-mono text-xs text-muted-foreground">{hint}</div>
      )}
      <input
        id={id}
        aria-label={ariaLabel}
        type="file"
        accept={accept}
        disabled={disabled}
        className="sr-only"
        onChange={(e) => take(e.target.files?.[0])}
      />
    </label>
  )
}
```

- [ ] **Step 4: Прогнать — проходит**

Run: `npx vitest run src/components/Dropzone.test.tsx`
Expected: PASS (4 теста).

- [ ] **Step 5: Полный гейт + коммит**

Run: `npm run typecheck && npm run lint && npm run format:check && npm run test`
Expected: всё зелёное.
```bash
git add frontend/src/components/Dropzone.tsx frontend/src/components/Dropzone.test.tsx
git commit -m "feat(front): общий компонент Dropzone (drag-and-drop, без зависимостей)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: TemplateUpload на Dropzone

**Files:**
- Modify: `frontend/src/components/articles/TemplateUpload.tsx`
- Test: `frontend/src/components/articles/TemplateUpload.test.tsx`

**Interfaces:**
- Consumes: `Dropzone` (Task 1) — `onFile: (file: File) => void`, пропсы `accept/id/ariaLabel/idleText/hint/disabled`.
- Produces: тот же `TemplateUpload` с пропом `onApplied`.

> Меняется ТОЛЬКО выбор файла. Превью/`Collapsible`/force-`Alert`+`Checkbox`/409/«Применить» — без изменений.

- [ ] **Step 1: Базовая линия тестов зелёная**

Run: `npx vitest run src/components/articles/TemplateUpload.test.tsx`
Expected: PASS (5 тестов) — фиксируем точку отсчёта. Хелпер `pick()` использует
`userEvent.upload(screen.getByLabelText(/файл шаблона/i), …)`.

- [ ] **Step 2: Подключить Dropzone, изменить onPick**

В `frontend/src/components/articles/TemplateUpload.tsx`:

Импорты: удалить `import { Input } from "@/components/ui/input"`; добавить
`import { Dropzone } from "@/components/Dropzone"`. (Импорт `Label` ОСТАВИТЬ — он используется
в force-Checkbox.)

Заменить сигнатуру и тело `onPick` (убрать чтение из события и проверку на null — `Dropzone`
отдаёт уже валидный `File`):
```tsx
  async function onPick(f: File) {
    // смена файла сбрасывает предыдущее превью, согласие и флаг конфликта
    setPreview(null)
    setConsent(false)
    setConflict(false)
    setFile(f)
    setBusy(true)
    try {
      setPreview(await importTemplate(f, { dryRun: true, force: false }))
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Не удалось прочитать файл"
      )
    } finally {
      setBusy(false)
    }
  }
```

Заменить блок выбора файла (текущие `<Label htmlFor="tpl-file">` + `<Input type="file">`) на
`Dropzone` + строку с именем файла:
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
      {file && (
        <p className="mt-2 text-xs text-muted-foreground">Файл: {file.name}</p>
      )}

      {busy && <p className="mt-2 text-muted-foreground">Обработка…</p>}
```
(Остальной JSX — `{preview && (...)}` блок — без изменений.)

- [ ] **Step 3: Прогнать TemplateUpload-тесты**

Run: `npx vitest run src/components/articles/TemplateUpload.test.tsx`
Expected: PASS (5 тестов). `getByLabelText(/файл шаблона/i)` резолвится через
`aria-label="Файл шаблона"` у скрытого input внутри `Dropzone`; `userEvent.upload` запускает
`onChange` → `onPick`.

Если какой-то из 5 тестов упадёт из-за того, что `Dropzone` блокирует upload при `disabled={busy}`
в момент загрузки — это не должно случиться (upload файла происходит, когда `busy=false`); если
всплывёт, НЕ ослабляй тест, разберись и сообщи.

- [ ] **Step 4: Полный гейт + коммит**

Run: `npm run typecheck && npm run lint && npm run format:check && npm run test`
```bash
git add frontend/src/components/articles/TemplateUpload.tsx frontend/src/components/articles/TemplateUpload.test.tsx
git commit -m "feat(front): TemplateUpload — выбор файла через общий Dropzone

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

(Тест-файл, скорее всего, не потребует правок; включён в `git add` на случай мелкой подгонки. Если
не менялся — `git add` его проигнорирует.)

---

## Task 3: StartScreen на Dropzone

**Files:**
- Modify: `frontend/src/pages/estimate/StartScreen.tsx`

**Interfaces:**
- Consumes: `Dropzone` (Task 1).
- Produces: тот же `StartScreen` с пропом `onFile: (file: File) => void`.

> Поведение и тексты сохраняются. Тесты `StartProcessing.test.tsx`, `EstimateFlow.test.tsx`,
> `App.test.tsx` НЕ меняются — `getByLabelText(/файл сметы/i)` резолвится через `ariaLabel`.

- [ ] **Step 1: Базовая линия зелёная**

Run: `npx vitest run src/pages/estimate/StartProcessing.test.tsx src/pages/estimate/EstimateFlow.test.tsx src/App.test.tsx`
Expected: PASS — фиксируем точку отсчёта (все используют `getByLabelText(/файл сметы/i)`).

- [ ] **Step 2: Переписать StartScreen на Dropzone**

Заменить `frontend/src/pages/estimate/StartScreen.tsx` целиком:
```tsx
import { Dropzone } from "@/components/Dropzone"

interface StartScreenProps {
  onFile: (file: File) => void
}

export function StartScreen({ onFile }: StartScreenProps) {
  return (
    <div className="p-8">
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
    </div>
  )
}
```
(`useState` и прямой импорт `UploadCloud` больше не нужны — уехали в `Dropzone`.)

- [ ] **Step 3: Прогнать затронутые тесты**

Run: `npx vitest run src/pages/estimate/StartProcessing.test.tsx src/pages/estimate/EstimateFlow.test.tsx src/App.test.tsx`
Expected: PASS — выбор файла (`userEvent.upload` по `getByLabelText(/файл сметы/i)`) вызывает
`onFile`; валидация `.xlsx`/`.xls` обеспечивается выводом расширений из `accept` в `Dropzone`.

- [ ] **Step 4: Полный гейт + коммит**

Run: `npm run typecheck && npm run lint && npm run format:check && npm run test`
```bash
git add frontend/src/pages/estimate/StartScreen.tsx
git commit -m "refactor(front): StartScreen на общий Dropzone (без дублирующей вёрстки)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Финал

- [ ] **Проверка отсутствия дублирования и сырого input**

Run:
```bash
grep -rn "type=\"file\"" frontend/src/components/articles frontend/src/pages/estimate || echo "OK: сырых file-input в потребителях нет"
grep -rn "onDragOver" frontend/src/pages/estimate/StartScreen.tsx || echo "OK: инлайн drag-вёрстки в StartScreen нет"
```
Expected: `type="file"` встречается только внутри `Dropzone.tsx`; в `StartScreen.tsx` нет инлайн drag-обработчиков.

- [ ] **Финальный полный гейт**

Run (из `frontend/`): `npm run typecheck && npm run lint && npm run format:check && npm run test && npm run build`
Expected: всё зелёное, прод-сборка успешна.

---

## Self-Review (выполнено при написании плана)

1. **Spec coverage:** Task 1 = компонент `Dropzone` + тесты; Task 2 = `TemplateUpload` на `Dropzone`
   (safety-флоу не тронут); Task 3 = `StartScreen` на `Dropzone`. Критерии готовности спеки
   (нет дубль-вёрстки, нет сырого input, нет новых зависимостей, полный гейт) покрыты финальной секцией.
2. **Placeholder scan:** плейсхолдеров нет — весь код компонента, тестов и правок приведён полностью.
3. **Type consistency:** `Dropzone` пропсы (`onFile/accept/id/ariaLabel/disabled/idleText/hotText/hint/className`)
   одинаковы в определении (Task 1) и во всех вызовах (Task 2/3). `onFile: (file: File) => void`
   согласован с `onPick(f: File)` в TemplateUpload и `onFile` в StartScreen.
4. **Риски:** (а) `getByLabelText` резолвится через `aria-label` скрытого input — проверяется
   базовыми прогонами в Task 2/3 Step 1; (б) `userEvent.upload` на `disabled` input — no-op в
   user-event v14, тест в Task 1 это фиксирует; (в) drop-валидация расширения единым `matchesAccept`
   (нет дублирования regex).
