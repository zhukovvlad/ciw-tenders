# UX этап 3: консистентность и демо-лоск — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Единый табличный язык на пяти поверхностях, политика фидбека (4 ножки), адаптивный минимум, хелпер плюрализации, персист аномалий структуры.

**Architecture:** Спека — [2026-07-04-ux-stage3-consistency-design.md](../specs/2026-07-04-ux-stage3-consistency-design.md). Новый модуль `ds-table.tsx` (обёртки над shadcn + классы-константы) — единственный источник табличного стиля; `promotableCount` в `reviewState.ts` — зеркало серверного предиката фонда; аномалии структуры персистятся в `estimates` (JSONB + int) и читаются фронтом из первичного `GET`.

**Tech Stack:** React 19 + TS strict + Tailwind v4 + shadcn/ui + vitest/RTL; FastAPI + SQLAlchemy + Alembic + pytest.

## Global Constraints

- Ветка: `feat/ux-stage3-consistency` от `docs/ux-stage3-spec` (спека и план едут в том же PR).
- `frontend/src/components/ui/` — вендорные shadcn-файлы, **не править**.
- Бэкенд только через `uv run` (никакого системного python/pip); `from __future__ import annotations` + type hints; ruff line-length 100.
- Фронтенд: prettier printWidth 80, импорты через `@/`, `erasableSyntaxOnly` (без enum/parameter properties). Все тексты UI — по-русски.
- Windows: кириллица в stdout — при необходимости `$env:PYTHONIOENCODING="utf-8"`. Порт бэка 8260. Файлы в LF.
- Команды тестов: фронт `cd frontend; npx vitest run <файл>`; бэк `cd backend; uv run pytest <файл> -q`. Полный прогон — `just test` из корня.
- Коммиты кончаются на `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Бэкенд — персист аномалий структуры

**Files:**
- Modify: `backend/app/domain/entities.py` (dataclass'ы `NewEstimate`, `Estimate`)
- Modify: `backend/app/infrastructure/db/models.py` (`EstimateModel`)
- Create: `backend/alembic/versions/0009_estimate_structure_anomalies.py`
- Modify: `backend/app/infrastructure/db/estimate_repository.py` (`create`, `_to_entity`)
- Modify: `backend/app/services/estimate_service.py` (`ingest`)
- Modify: `backend/app/api/schemas.py` (`EstimateDetailOut`)
- Modify: `backend/tests/fakes.py` (`FakeEstimateRepository.create`)
- Test: `backend/tests/test_estimate_routes.py`

**Interfaces:**
- Consumes: `ParsedEstimate.anomalies: list[StructuralAnomaly]`, `.outline_overrides: int` (парсер, уже есть).
- Produces: `GET /estimates/{id}` → поля `anomalies: list[{kind, source_index, code, name, detail}]` и `outline_overrides: int` (Task 12 читает их на фронте).

- [ ] **Step 1: Написать падающие тесты**

Тест на аномалии в `GET` обязан использовать **тот же xlsx и тот же ожидаемый `kind`**, что и соседний `test_upload_response_carries_anomalies_and_outline_overrides` (строки 231–240 того же файла) — именно этот тест уже кодирует, при какой конфигурации строк парсер считает дубль кода аномалией (в домене дубли кодов сами по себе легальны — это знание живёт в парсере, не выдумывать новую конфигурацию). Переиспользовать буквально: тот же вызов `_xlsx_rows([("1", "A", "СМР"), ("1.1", "B", None), ("1.1", "C", None)])` и тот же ассерт `any(a["kind"] == "duplicate_code" for a in ...)`.

В `backend/tests/test_estimate_routes.py` после `test_upload_response_carries_anomalies_and_outline_overrides` добавить:

```python
def test_get_estimate_returns_persisted_anomalies() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    client = _client(repo, storage)
    # та же фикстура и тот же ожидаемый kind, что в
    # test_upload_response_carries_anomalies_and_outline_overrides выше —
    # это знание принадлежит парсеру, не дублировать своей конфигурацией
    content = _xlsx_rows([("1", "A", "СМР"), ("1.1", "B", None), ("1.1", "C", None)])
    resp = client.post("/api/estimates", files={"file": ("e.xlsx", content, _XLSX)})
    assert resp.status_code == 201
    eid = resp.json()["id"]
    detail = client.get(f"/api/estimates/{eid}")
    assert detail.status_code == 200
    body = detail.json()
    assert any(a["kind"] == "duplicate_code" for a in body["anomalies"])
    assert isinstance(body["outline_overrides"], int)


def test_get_estimate_defaults_anomalies_to_empty_without_upload() -> None:
    # сущность без аномалий (сеется напрямую через фейк-репозиторий, минуя
    # ingest) → API отдаёт пустые дефолты. НЕ проверяет NULL-ветку чтения
    # JSONB на реальной БД (m.structure_anomalies or [] в estimate_repository) —
    # та ветка тривиальна (or []) и глазами проверяется на живой dev-БД
    # открытием сметы, созданной до миграции 0009 (Task 13, живой гейт).
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    client = _client(repo, storage)
    eid = _seed_reviewed(repo)
    detail = client.get(f"/api/estimates/{eid}")
    assert detail.status_code == 200
    assert detail.json()["anomalies"] == []
    assert detail.json()["outline_overrides"] == 0
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `cd backend; uv run pytest tests/test_estimate_routes.py -q`
Expected: FAIL — `KeyError: 'anomalies'` (поля нет в ответе GET). Если вместо этого первый тест падает на пустом `body["anomalies"]` — значит фикстура скопирована с отклонением от соседнего upload-теста; сверить дословно.

- [ ] **Step 3: Домен — расширить `NewEstimate` и `Estimate`**

В `backend/app/domain/entities.py`:

```python
@dataclass(frozen=True, slots=True)
class NewEstimate:
    """Данные для создания сметы (до записи)."""

    user_id: int
    filename: str
    original_object_key: str
    anomalies: list[StructuralAnomaly] = field(default_factory=list)
    outline_overrides: int = 0
```

В `Estimate` (после `completed_at`) добавить:

```python
    anomalies: list[StructuralAnomaly] = field(default_factory=list)  # аномалии парсинга (этап 3 UX)
    outline_overrides: int = 0  # агрегат outline_code_mismatch (см. StructuralAnomaly)
```

- [ ] **Step 4: ORM-модель + миграция**

В `EstimateModel` (`backend/app/infrastructure/db/models.py`, после `completed_at`):

```python
    structure_anomalies: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    outline_overrides: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
```

(`JSONB`, `Integer`, `text` уже импортированы — используются `candidates` / `is_reference`.)

Создать `backend/alembic/versions/0009_estimate_structure_anomalies.py`:

```python
"""estimates.structure_anomalies + outline_overrides — персист аномалий структуры (этап 3 UX)."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "estimates",
        sa.Column("structure_anomalies", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "estimates",
        sa.Column("outline_overrides", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("estimates", "outline_overrides")
    op.drop_column("estimates", "structure_anomalies")
```

- [ ] **Step 5: Репозиторий — запись в `create`, чтение в `_to_entity`**

`backend/app/infrastructure/db/estimate_repository.py`. Добавить импорты: `from dataclasses import asdict` (если нет) и `StructuralAnomaly` в импорт из `app.domain.entities`.

В `create()` — конструктор `EstimateModel`:

```python
            est = EstimateModel(
                user_id=new.user_id,
                filename=new.filename,
                original_object_key=new.original_object_key,
                status="pending",
                structure_anomalies=[asdict(a) for a in new.anomalies],
                outline_overrides=new.outline_overrides,
            )
```

В `_to_entity()` — в конструктор `Estimate` добавить (толерантное чтение: лишние/отсутствующие ключи JSONB не роняют чтение — спека §10):

```python
            anomalies=[
                StructuralAnomaly(
                    kind=a.get("kind", ""),
                    source_index=a.get("source_index", 0),
                    code=a.get("code", ""),
                    name=a.get("name", ""),
                    detail=a.get("detail", ""),
                )
                for a in (m.structure_anomalies or [])
            ],
            outline_overrides=m.outline_overrides,
```

- [ ] **Step 6: Сервис — момент записи это транзакция ingest**

`backend/app/services/estimate_service.py`, в `ingest()`:

```python
        estimate = self._repository.create(
            NewEstimate(
                user_id=owner_id,
                filename=filename,
                original_object_key=key,
                anomalies=parsed.anomalies,
                outline_overrides=parsed.outline_overrides,
            ),
            parsed.nodes,
        )
```

- [ ] **Step 7: DTO — `EstimateDetailOut`**

`backend/app/api/schemas.py`: добавить `from dataclasses import asdict` (если нет). В `EstimateDetailOut` — поля:

```python
    anomalies: list[StructuralAnomalyOut] = []
    outline_overrides: int = 0
```

и в `from_entity()` — в вызов `cls(...)`:

```python
            anomalies=[StructuralAnomalyOut(**asdict(a)) for a in e.anomalies],
            outline_overrides=e.outline_overrides,
```

- [ ] **Step 8: Фейк-репозиторий**

`backend/tests/fakes.py`, `FakeEstimateRepository.create()` — в конструктор `Estimate(...)` добавить:

```python
            anomalies=list(new.anomalies),
            outline_overrides=new.outline_overrides,
```

- [ ] **Step 9: Прогнать тесты**

Run: `cd backend; uv run pytest tests/test_estimate_routes.py -q` → PASS (`test_get_estimate_returns_persisted_anomalies`, `test_get_estimate_defaults_anomalies_to_empty_without_upload` + все старые).
Run: `cd backend; uv run pytest -q` → PASS (ничего не сломано).
Run: `cd backend; uv run ruff check .` → чисто.

- [ ] **Step 10: Применить миграцию к dev-БД**

Run: `just migrate`
Expected: `Running upgrade 0008 -> 0009`.

- [ ] **Step 11: Commit**

```bash
git add backend/
git commit -m "feat(estimates): персист аномалий структуры — JSONB в estimates + отдача в GET (этап 3 UX)"
```

---

### Task 2: Хелпер плюрализации `pluralizeRu`

**Files:**
- Create: `frontend/src/lib/plural.ts`
- Test: `frontend/src/lib/plural.test.ts`

**Interfaces:**
- Produces: `pluralizeRu(n: number, forms: [one: string, few: string, many: string]): string` — возвращает форму слова (без числа); Task 3 и 8 используют.

- [ ] **Step 1: Написать падающий тест**

`frontend/src/lib/plural.test.ts`:

```ts
import { describe, expect, it } from "vitest"
import { pluralizeRu } from "./plural"

const FORMS: [string, string, string] = [
  "замечание",
  "замечания",
  "замечаний",
]

describe("pluralizeRu", () => {
  it.each([
    [1, "замечание"],
    [21, "замечание"],
    [101, "замечание"],
    [2, "замечания"],
    [4, "замечания"],
    [22, "замечания"],
    [5, "замечаний"],
    [11, "замечаний"],
    [12, "замечаний"],
    [14, "замечаний"],
    [111, "замечаний"],
    [0, "замечаний"],
  ])("%i → %s", (n, expected) => {
    expect(pluralizeRu(n, FORMS)).toBe(expected)
  })
})
```

- [ ] **Step 2: Убедиться, что падает**

Run: `cd frontend; npx vitest run src/lib/plural.test.ts`
Expected: FAIL — модуль `./plural` не существует.

- [ ] **Step 3: Реализация**

`frontend/src/lib/plural.ts`:

```ts
// Русская плюрализация: forms = [один, несколько, много]
// («замечание», «замечания», «замечаний»). Возвращает форму — число
// подставляет вызывающий. Задел под i18n (этап 4): вызовы точечно заменятся
// i18next-плюрализацией, места уже параметризованы.
export function pluralizeRu(
  n: number,
  forms: [one: string, few: string, many: string]
): string {
  const abs = Math.abs(n)
  const mod10 = abs % 10
  const mod100 = abs % 100
  if (mod10 === 1 && mod100 !== 11) return forms[0]
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20))
    return forms[1]
  return forms[2]
}
```

- [ ] **Step 4: Тест зелёный**

Run: `cd frontend; npx vitest run src/lib/plural.test.ts` → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/plural.ts frontend/src/lib/plural.test.ts
git commit -m "feat(i18n): хелпер плюрализации pluralizeRu (задел под этап 4)"
```

---

### Task 3: Применение плюрализации

**Files:**
- Modify: `frontend/src/components/estimate/StructureNotice.tsx` (убрать `pluralizeZamechanie`, «строк(ах)»)
- Modify: `frontend/src/pages/estimate/ReviewScreen.tsx:237` (диалог завершения)
- Modify: `frontend/src/components/articles/TemplateUpload.tsx:122` («Импорт удалит N строк»)
- Tests: существующие `StructureNotice.test.tsx` (проверки рендером — менять не должно понадобиться), `ReviewScreen.test.tsx`, `TemplateUpload.test.tsx` — обновить ассерты на новые тексты, если матчатся старые.

**Interfaces:**
- Consumes: `pluralizeRu` из Task 2.

- [ ] **Step 1: StructureNotice**

Удалить функцию `pluralizeZamechanie` (строки 38–45). Импорт: `import { pluralizeRu } from "@/lib/plural"`. Заголовок:

```tsx
  const title =
    anomalies.length > 0
      ? `Структура сметы: ${anomalies.length} ${pluralizeRu(anomalies.length, ["замечание", "замечания", "замечаний"])}`
      : "Структура сметы"
```

Агрегатная строка (строка 107):

```tsx
          <p className="px-3 py-2 text-xs text-muted-foreground">
            В {outlineOverrides}{" "}
            {pluralizeRu(outlineOverrides, ["строке", "строках", "строках"])}{" "}
            вложенность взята из группировки
          </p>
```

- [ ] **Step 2: ReviewScreen — диалог завершения**

Импорт `pluralizeRu`. Текст `AlertDialogDescription` (строка 237):

```tsx
                    <AlertDialogDescription>
                      Без решения — {pending}{" "}
                      {pluralizeRu(pending, [
                        "спорная строка",
                        "спорные строки",
                        "спорных строк",
                      ])}
                      . Завершить всё равно? Возобновить можно в любой момент.
                    </AlertDialogDescription>
```

Счётчик в шапке «спорных решено {reviewed} из {total}» НЕ меняется — форма инвариантна к числу (родительный множественного при любом N).

- [ ] **Step 3: TemplateUpload**

Импорт `pluralizeRu`. Строка 122:

```tsx
                    : `Импорт удалит ${preview.deleted} ${pluralizeRu(preview.deleted, ["строку", "строки", "строк"])} (снос корня или большой доли). Это необратимо.`}
```

«Пропущено строк: N» (строка 105) не трогать — форма с числом после двоеточия инвариантна (спека §6).

- [ ] **Step 4: Прогнать тесты, поправить ассерты старых текстов**

Run: `cd frontend; npx vitest run src/components/estimate/StructureNotice.test.tsx src/pages/estimate/ReviewScreen.test.tsx src/components/articles/TemplateUpload.test.tsx`

Если ассерты матчат старые фразы («Осталось … спорных строк без решения», «Импорт удалит … строк (», «строк(ах)») — заменить ожидания на новые тексты из Step 1–3. Затем полный прогон: `cd frontend; npx vitest run` → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(ux): плюрализация через pluralizeRu — StructureNotice, диалог завершения, импорт шаблона"
```

---

### Task 4: Модуль `ds-table` — источник табличного стиля

**Files:**
- Create: `frontend/src/components/common/ds-table.tsx`
- Test: `frontend/src/components/common/ds-table.test.tsx`

**Interfaces:**
- Produces (Task 5–7 используют):
  - компоненты `DsTable`, `DsTableHeader`, `DsTableBody`, `DsTableRow` (проп `interactive?: boolean`), `DsTableHead`, `DsTableCell`;
  - константы `dsHeadCellClass: string`, `dsCellClass: string`, `dsHairline: string`, `dsHeadRowClass: string`.

- [ ] **Step 1: Написать падающий тест**

`frontend/src/components/common/ds-table.test.tsx`:

```tsx
import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import {
  DsTable,
  DsTableBody,
  DsTableCell,
  DsTableHead,
  DsTableHeader,
  DsTableRow,
} from "./ds-table"

function renderRows() {
  return render(
    <DsTable>
      <DsTableHeader>
        <DsTableRow>
          <DsTableHead>Колонка</DsTableHead>
        </DsTableRow>
      </DsTableHeader>
      <DsTableBody>
        <DsTableRow data-testid="plain">
          <DsTableCell>обычная</DsTableCell>
        </DsTableRow>
        <DsTableRow data-testid="clickable" interactive>
          <DsTableCell>кликабельная</DsTableCell>
        </DsTableRow>
      </DsTableBody>
    </DsTable>
  )
}

describe("ds-table", () => {
  it("неинтерактивная строка активно гасит вендорный hover", () => {
    renderRows()
    const row = screen.getByTestId("plain")
    expect(row.className).toContain("hover:bg-transparent")
    expect(row.className).not.toContain("hover:bg-muted/50")
    expect(row.className).not.toContain("cursor-pointer")
  })

  it("интерактивная строка сохраняет hover и получает cursor-pointer", () => {
    renderRows()
    const row = screen.getByTestId("clickable")
    expect(row.className).toContain("hover:bg-muted/50")
    expect(row.className).toContain("cursor-pointer")
  })

  it("ячейка шапки несёт DS-канон: uppercase text-xs, вендорный h-10 погашен", () => {
    renderRows()
    const head = screen.getByRole("columnheader", { name: "Колонка" })
    expect(head.className).toContain("uppercase")
    expect(head.className).toContain("h-auto")
    expect(head.className).not.toContain("font-medium")
  })
})
```

- [ ] **Step 2: Убедиться, что падает**

Run: `cd frontend; npx vitest run src/components/common/ds-table.test.tsx`
Expected: FAIL — модуль не существует.

- [ ] **Step 3: Реализация**

`frontend/src/components/common/ds-table.tsx`:

```tsx
// Единственный источник табличного стиля MR DS (спека этапа 3 §3):
// обёртки над shadcn-примитивами (ui/table.tsx — вендорный, не правится)
// + классы-константы для поверхностей, которые не могут быть <table>
// (виртуализированный ReviewGrid, ContextStrip).
import * as React from "react"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"

/** Ячейка шапки. h-auto гасит вендорный h-10, font-normal — font-medium. */
export const dsHeadCellClass =
  "h-auto px-4 py-2.5 text-xs font-normal tracking-wide uppercase text-muted-foreground"
/** Ячейка тела. whitespace-normal гасит вендорный nowrap (длинные наименования). */
export const dsCellClass = "px-4 py-2 text-sm whitespace-normal"
/** Цвет границ табличного семейства. */
export const dsHairline = "border-[var(--ds-hairline)]"
/** Фон ряда шапки. */
export const dsHeadRowClass = "bg-[var(--ds-surface-sunken)]"

export const DsTable = Table
export const DsTableBody = TableBody

export function DsTableHeader({
  className,
  ...props
}: React.ComponentProps<typeof TableHeader>) {
  return <TableHeader className={cn(dsHeadRowClass, className)} {...props} />
}

export function DsTableHead({
  className,
  ...props
}: React.ComponentProps<typeof TableHead>) {
  return <TableHead className={cn(dsHeadCellClass, className)} {...props} />
}

interface DsTableRowProps extends React.ComponentProps<typeof TableRow> {
  /**
   * Кликабельность КОНКРЕТНОЙ строки, не поверхности (спека §2): hover —
   * только там, где клик что-то делает. Вендорный TableRow несёт
   * hover:bg-muted/50 всегда; tailwind-merge заменяет конфликтующие классы,
   * но не удаляет — неинтерактивный вариант гасит его hover:bg-transparent.
   */
  interactive?: boolean
}

export function DsTableRow({
  className,
  interactive = false,
  ...props
}: DsTableRowProps) {
  return (
    <TableRow
      className={cn(
        dsHairline,
        interactive ? "cursor-pointer" : "hover:bg-transparent",
        className
      )}
      {...props}
    />
  )
}

export function DsTableCell({
  className,
  ...props
}: React.ComponentProps<typeof TableCell>) {
  return <TableCell className={cn(dsCellClass, className)} {...props} />
}
```

- [ ] **Step 4: Тест зелёный**

Run: `cd frontend; npx vitest run src/components/common/ds-table.test.tsx` → PASS.
Run: `cd frontend; npm run typecheck` → чисто.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/common
git commit -m "feat(ux): ds-table — единый источник табличного стиля (обёртки shadcn + константы)"
```

---

### Task 5: Миграция EstimateList и StructureNotice на DsTable

**Files:**
- Modify: `frontend/src/components/estimate/EstimateList.tsx`
- Modify: `frontend/src/components/estimate/StructureNotice.tsx`
- Test: `frontend/src/components/estimate/EstimateList.test.tsx`

**Interfaces:**
- Consumes: `DsTable*` из Task 4; `metaFor(status).clickable` (уже в EstimateList).

- [ ] **Step 1: Падающий тест — hover следует кликабельности строки**

Проверено: фикстура `ITEMS` в `EstimateList.test.tsx` (строки 19–34) уже содержит `ready.xlsx` (clickable) и `blocked.xlsx` (не clickable) — переиспользуется как есть. Добавить:

```tsx
  it("hover следует кликабельности: blocked-строка без cursor-pointer", async () => {
    vi.spyOn(estimatesApi, "listEstimates").mockResolvedValue({
      items: ITEMS,
      total: ITEMS.length,
    })
    render(<EstimateList onOpen={vi.fn()} />)
    const readyRow = (await screen.findByText("ready.xlsx")).closest("tr")!
    const blockedRow = screen.getByText("blocked.xlsx").closest("tr")!
    expect(readyRow.className).toContain("cursor-pointer")
    expect(blockedRow.className).not.toContain("cursor-pointer")
    expect(blockedRow.className).toContain("hover:bg-transparent")
  })
```

Run: `cd frontend; npx vitest run src/components/estimate/EstimateList.test.tsx` → новый тест FAIL.

- [ ] **Step 2: EstimateList — заменить импорты и компоненты**

Импорт таблицы (строки 17–24) заменить на:

```tsx
import {
  DsTable,
  DsTableBody,
  DsTableCell,
  DsTableHead,
  DsTableHeader,
  DsTableRow,
} from "@/components/common/ds-table"
```

В JSX: `Table`→`DsTable`, `TableHeader`→`DsTableHeader`, `TableRow`→`DsTableRow`, `TableHead`→`DsTableHead`, `TableBody`→`DsTableBody`, `TableCell`→`DsTableCell`. Строке тела передать интерактивность:

```tsx
              <DsTableRow key={item.id} interactive={meta.clickable}>
```

(шапочная `DsTableRow` — без `interactive`).

- [ ] **Step 3: StructureNotice — то же самое**

Импорт (строки 8–15) заменить на `DsTable*` из `@/components/common/ds-table`, компоненты в JSX — соответственно. `interactive` нигде не передавать (строки аномалий некликабельны). `className="text-xs …"` на ячейках остаются (побеждают `text-sm` из `dsCellClass` через `cn`).

- [ ] **Step 4: Тесты зелёные**

Run: `cd frontend; npx vitest run src/components/estimate/` → PASS (включая новый).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/estimate
git commit -m "refactor(ux): EstimateList и StructureNotice — на ds-table (DS-канон, hover по кликабельности)"
```

---

### Task 6: Миграция ArticleTable на DsTable

**Files:**
- Modify: `frontend/src/components/articles/ArticleTable.tsx`
- Test: `frontend/src/components/articles/ArticleTable.test.tsx` (существующие тесты должны остаться зелёными)

**Interfaces:**
- Consumes: `DsTable*` из Task 4.

- [ ] **Step 1: Заменить сырой `<table>`**

Импорт: `DsTable, DsTableBody, DsTableCell, DsTableHead, DsTableHeader, DsTableRow` из `@/components/common/ds-table`. JSX таблицы (строки 48–100) переписать:

```tsx
      <DsTable>
        <DsTableHeader>
          <DsTableRow>
            <DsTableHead>Код</DsTableHead>
            <DsTableHead>Наименование</DsTableHead>
            {isAdmin && <DsTableHead className="w-10" />}
          </DsTableRow>
        </DsTableHeader>
        <DsTableBody>
          {filtered.map((a) => {
            const depth = a.article_code.split(".").length - 1
            return (
              <DsTableRow key={a.id}>
                <DsTableCell className="font-mono text-xs">
                  {a.article_code}
                </DsTableCell>
                <DsTableCell
                  style={{ paddingLeft: `${1 + depth * 1.25}rem` }}
                >
                  {a.name}
                </DsTableCell>
                {isAdmin && (
                  <DsTableCell>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <button type="button" aria-label="Удалить">
                          <Trash2 className="size-4 text-destructive" />
                        </button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Удалить статью?</AlertDialogTitle>
                          <AlertDialogDescription>
                            «{a.name}» ({a.article_code}) будет удалена.
                            Действие необратимо.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Отмена</AlertDialogCancel>
                          <AlertDialogAction onClick={() => onDelete?.(a.id)}>
                            Удалить
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </DsTableCell>
                )}
              </DsTableRow>
            )
          })}
        </DsTableBody>
      </DsTable>
```

Блок `AlertDialog` (строки 72–93) переносится внутрь ячейки без изменений. Визуальные отличия от старого: бордер сверху строк становится `border-b` (как у всех DS-таблиц), появляется `overflow-x-auto` (обёртка shadcn Table) — это и есть цель.

- [ ] **Step 2: Тесты зелёные**

Run: `cd frontend; npx vitest run src/components/articles/ArticleTable.test.tsx` → PASS (роли table/row/cell сохраняются — shadcn рендерит настоящий `<table>`).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/articles/ArticleTable.tsx
git commit -m "refactor(ux): ArticleTable — с сырого <table> на ds-table (+overflow-x бесплатно)"
```

---

### Task 7: ReviewGrid и ContextStrip — константы, hover, min-w

**Files:**
- Modify: `frontend/src/pages/estimate/ReviewGrid.tsx`
- Modify: `frontend/src/pages/estimate/ContextStrip.tsx`
- Modify: `docs/TECH_DEBT.md` (магическая высота грида)
- Test: `frontend/src/pages/estimate/ReviewGrid.test.tsx`

**Interfaces:**
- Consumes: `dsHeadCellClass`, `dsHeadRowClass`, `dsHairline` из Task 4; вычисленный `clickable` (уже в ReviewGrid).

- [ ] **Step 1: Падающий тест — hover только у кликабельных строк**

В `ReviewGrid.test.tsx` добавить самодостаточный блок (если в файле уже есть фабрика `MatchRow` — использовать её вместо `HOVER_BASE`, сохранив статусы и имена):

```tsx
const HOVER_BASE: MatchRow = {
  row_number: 1,
  section_code: "1",
  source_name: "Работа",
  sourceIndex: 0,
  breadcrumb: [],
  matchError: null,
  status: "needs_review",
  score: 0.7,
  matched_code: "01.01",
  matched_name: "Статья",
  matched_article_id: 7,
  matchedBreadcrumb: [],
  candidates: [],
  review_status: "unreviewed",
  final_article_id: null,
  finalBreadcrumb: [],
  final_code: null,
  final_name: null,
}

describe("hover по кликабельности (этап 3)", () => {
  const rows: MatchRow[] = [
    { ...HOVER_BASE, row_number: 1, source_name: "Кликабельная работа" },
    {
      ...HOVER_BASE,
      row_number: 2,
      sourceIndex: 1,
      source_name: "Орг-заголовок",
      status: "excluded",
    },
  ]
  const rect = { width: 1024, height: 600 }

  it("с onOpenRow: hover и cursor у решаемой строки, у excluded — нет", () => {
    render(
      <ReviewGrid
        state={initReview("f.xlsx", rows)}
        dispatch={vi.fn()}
        onOpenRow={vi.fn()}
        scrollOffsetRef={{ current: null }}
        initialRect={rect}
      />
    )
    const clickable = screen
      .getByText("Кликабельная работа")
      .closest('[role="row"]')!
    const excluded = screen
      .getByText("Орг-заголовок")
      .closest('[role="row"]')!
    expect(clickable.className).toContain("hover:bg-muted/50")
    expect(clickable.className).toContain("cursor-pointer")
    expect(excluded.className).not.toContain("hover:bg-muted/50")
    expect(excluded.className).not.toContain("cursor-pointer")
  })

  it("read-only (без onOpenRow): hover нет ни у кого", () => {
    render(
      <ReviewGrid
        state={initReview("f.xlsx", rows)}
        dispatch={vi.fn()}
        scrollOffsetRef={{ current: null }}
        initialRect={rect}
      />
    )
    const row = screen
      .getByText("Кликабельная работа")
      .closest('[role="row"]')!
    expect(row.className).not.toContain("hover:bg-muted/50")
    expect(row.className).not.toContain("cursor-pointer")
  })
})
```

(импорты `MatchRow` из `@/lib/types` и `initReview` из `@/lib/reviewState` — добавить, если их нет в файле).

Run: `cd frontend; npx vitest run src/pages/estimate/ReviewGrid.test.tsx` → новые тесты FAIL (hover-класса ещё нет вовсе).

- [ ] **Step 2: ReviewGrid — общие константы + hover + min-w-обёртка**

Импорты:

```tsx
import { cn } from "@/lib/utils"
import {
  dsHairline,
  dsHeadCellClass,
  dsHeadRowClass,
} from "@/components/common/ds-table"
```

Шапка (строки 128–134):

```tsx
        <div
          role="row"
          className={cn(
            "sticky top-0 z-10 grid items-center text-left",
            dsHeadRowClass,
            dsHeadCellClass,
            GRID_COLS
          )}
        >
```

Строка (строки 175–181):

```tsx
                className={cn(
                  "grid items-center border-b px-4 text-sm",
                  dsHairline,
                  GRID_COLS,
                  clickable && "cursor-pointer hover:bg-muted/50",
                  flagged && "border-l-2 border-l-[var(--warning)]",
                  contextRow && "opacity-60"
                )}
```

(строка `(clickable ? " cursor-pointer" : "")` удаляется — заменена веткой в `cn`).

min-w-обёртка (спека §5: охватывает шапку И полотно, внутри скролл-контейнера — иначе колонки уезжают из-под заголовков при горизонтальном скролле). Внутри `div ref={parentRef}` обернуть шапку и виртуализированное полотно:

```tsx
      <div
        ref={parentRef}
        onScroll={...}                       {/* без изменений */}
        className="relative h-[calc(100vh-184px)] overflow-auto"
        role="table"
      >
        <div className="min-w-[720px]">
          {/* шапка role="row" */}
          {/* полотно virtualizer.getTotalSize() */}
        </div>
      </div>
```

Значение `min-w-[720px]` — стартовое; уточняется на живом гейте (Task 13), правится одним числом.

- [ ] **Step 3: ContextStrip — константа границы**

```tsx
import { cn } from "@/lib/utils"
import { dsHairline } from "@/components/common/ds-table"
```

Строка 33: `className={cn("mt-3 rounded-md border text-xs", dsHairline)}`.
Граница раздела (строка 42) остаётся `border-[var(--ds-border-strong)]` — это НЕ hairline, это осознанно сильная граница.

- [ ] **Step 4: TECH_DEBT — магическая высота**

В `docs/TECH_DEBT.md` добавить пункт (формат — по соседним записям файла):

> **ReviewGrid: магическая высота `h-[calc(100vh-184px)]`** — оффсет зашит константой и молча ломается при изменении высоты шапки/тулбара. Перевести на flex-раскладку (`flex-1` + `min-h-0` по цепочке родителей). Отложено на этапе 3 UX (спека §9): компактный режим шапки высоту не менял.

- [ ] **Step 5: Тесты зелёные**

Run: `cd frontend; npx vitest run src/pages/estimate/` → PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/estimate docs/TECH_DEBT.md
git commit -m "refactor(ux): ReviewGrid/ContextStrip на константы ds-table; hover по clickable; min-w против сжатия колонок"
```

---

### Task 8: `promotableCount` + тумблер фонда в DoneScreen

**Files:**
- Modify: `frontend/src/lib/reviewState.ts` (новый хелпер)
- Modify: `frontend/src/pages/estimate/DoneScreen.tsx`
- Modify: `backend/app/services/decision_fund_service.py` (перекрёстный комментарий)
- Test: `frontend/src/lib/reviewState.test.ts`, `frontend/src/pages/estimate/DoneScreen.test.tsx`

**Interfaces:**
- Produces: `promotableCount(rows: MatchRow[]): number` в `@/lib/reviewState`.
- Consumes: `MatchRow.review_status`, `MatchRow.status` (типы `@/lib/types`).

- [ ] **Step 1: Падающие юнит-тесты хелпера**

В `reviewState.test.ts` добавить (базовую строку собрать литералом или переиспользовать фабрику файла, если есть):

```ts
import { promotableCount } from "./reviewState"
import type { MatchRow } from "./types"

const BASE: MatchRow = {
  row_number: 1,
  section_code: "1",
  source_name: "Работа",
  sourceIndex: 0,
  breadcrumb: [],
  matchError: null,
  status: "confident",
  score: 0.95,
  matched_code: "01.01",
  matched_name: "Статья",
  matched_article_id: 7,
  matchedBreadcrumb: [],
  candidates: [],
  review_status: "unreviewed",
  final_article_id: null,
  finalBreadcrumb: [],
  final_code: null,
  final_name: null,
}

describe("promotableCount — зеркало серверного предиката фонда", () => {
  it("unreviewed confident НЕ промоутабелен (авто-уверенность ≠ решение оператора)", () => {
    expect(promotableCount([BASE])).toBe(0)
  })
  it("confirmed промоутабелен", () => {
    expect(
      promotableCount([
        { ...BASE, status: "needs_review", review_status: "confirmed" },
      ])
    ).toBe(1)
  })
  it("overridden промоутабелен", () => {
    expect(
      promotableCount([
        { ...BASE, status: "needs_review", review_status: "overridden" },
      ])
    ).toBe(1)
  })
  it("подтверждённый фонд-хит НЕ промоутабелен (анти-накрутка)", () => {
    expect(
      promotableCount([
        { ...BASE, status: "matched_fund", review_status: "confirmed" },
      ])
    ).toBe(0)
  })
  it("overridden фонд-хит промоутабелен (механика конфликтов фонда)", () => {
    expect(
      promotableCount([
        { ...BASE, status: "matched_fund", review_status: "overridden" },
      ])
    ).toBe(1)
  })
})
```

Run: `cd frontend; npx vitest run src/lib/reviewState.test.ts` → FAIL (нет экспорта).

- [ ] **Step 2: Хелпер в reviewState.ts**

После `requiresDecision` добавить:

```ts
// ЗЕРКАЛО бэкового предиката промоушена в фонд (_PROMOTABLE_REVIEW +
// анти-накрутка, decision_fund_service.py): фонд пополняют confirmed/
// overridden-решения оператора, КРОМЕ подтверждённых фонд-хитов (фонд не
// рекрутируется из самого себя). При изменении правил фонда синхронизировать
// оба места — как пару REVIEWABLE ↔ _REVIEWABLE выше.
export function promotableCount(rows: MatchRow[]): number {
  return rows.filter(
    (r) =>
      (r.review_status === "confirmed" || r.review_status === "overridden") &&
      !(r.status === "matched_fund" && r.review_status === "confirmed")
  ).length
}
```

Run: `cd frontend; npx vitest run src/lib/reviewState.test.ts` → PASS.

- [ ] **Step 3: Перекрёстный комментарий на бэке**

`backend/app/services/decision_fund_service.py`, над `_PROMOTABLE_REVIEW` (строка 16):

```python
# ЗЕРКАЛО на фронте: promotableCount() в frontend/src/lib/reviewState.ts
# (включая анти-накрутку matched_fund+confirmed ниже) — при изменении правил
# синхронизировать оба места.
_PROMOTABLE_REVIEW = {"confirmed", "overridden"}
```

- [ ] **Step 4: Падающие тесты DoneScreen + починка дефолтной фикстуры**

`MOCK_ROWS` — все `review_status: "unreviewed"` ⇒ после ввода disabled существующие клики по тумблеру перестанут работать. В `DoneScreen.test.tsx` дефолтное состояние `renderDone` заменить на состояние с промоутабельной строкой:

```tsx
// хотя бы одна строка с решением оператора — иначе тумблер фонда disabled
// (promotableCount === 0) и тесты кликов по нему бессмысленны
const ROWS_WITH_DECISION = MOCK_ROWS.map((r, i) =>
  i === 0
    ? {
        ...r,
        status: "needs_review" as const,
        review_status: "confirmed" as const,
      }
    : r
)
```

и в `renderDone`: `state={initReview("смета.xlsx", ROWS_WITH_DECISION)}`.

Новые тесты:

```tsx
  it("тумблер disabled с пояснением, когда нет решений оператора", () => {
    renderDone({ state: initReview("смета.xlsx", MOCK_ROWS) }) // все unreviewed
    expect(screen.getByRole("switch")).toBeDisabled()
    expect(
      screen.getByText(/Фонд пополняют решения, принятые оператором/)
    ).toBeInTheDocument()
  })

  it("подтверждённые фонд-хиты не активируют тумблер (анти-накрутка)", () => {
    const rows = MOCK_ROWS.map((r, i) =>
      i === 0
        ? {
            ...r,
            status: "matched_fund" as const,
            review_status: "confirmed" as const,
          }
        : r
    )
    renderDone({ state: initReview("смета.xlsx", rows) })
    expect(screen.getByRole("switch")).toBeDisabled()
  })

  it("при наличии решения оператора тумблер активен и пояснение скрыто", () => {
    renderDone({})
    expect(screen.getByRole("switch")).toBeEnabled()
    expect(
      screen.queryByText(/Фонд пополняют решения/)
    ).not.toBeInTheDocument()
  })

  it("эталонная смета с 0 промоутабельных: тумблер активен для выключения", () => {
    // оператор возобновил проверку и переиграл всё в rejected — promotable=0,
    // но смета УЖЕ в фонде (isReference=true): unreference обязана остаться
    // доступной, disabled блокирует только ВКЛЮЧЕНИЕ, не выключение
    renderDone({
      state: initReview("смета.xlsx", MOCK_ROWS), // все unreviewed → promotable=0
      isReference: true,
    })
    expect(screen.getByRole("switch")).toBeEnabled()
    expect(
      screen.queryByText(/Фонд пополняют решения/)
    ).not.toBeInTheDocument()
  })
```

Run: `cd frontend; npx vitest run src/pages/estimate/DoneScreen.test.tsx` → новые FAIL.

- [ ] **Step 5: DoneScreen — disabled + пояснение**

Импорт: `import { decisionFor, promotableCount } from "@/lib/reviewState"`. После вычисления `noPair`:

```tsx
  const promotable = promotableCount(state.rows)
  // 0 промоутабельных блокирует ТОЛЬКО включение — уже эталонная смета
  // (inFund=true) обязана оставаться снимаемой всегда (unreference — законная
  // операция независимо от текущего состава решений, см. reverse-флоу фонда)
  const blockedByEmpty = promotable === 0 && !inFund
```

Блок тумблера (строки 97–107):

```tsx
      <div className="mt-6 flex items-center justify-center gap-3 text-left">
        <span className="text-sm text-[var(--ds-text-2)]">
          Эталонная смета — добавить в фонд решений
        </span>
        <Switch
          checked={inFund}
          disabled={estimateId === null || blockedByEmpty}
          onCheckedChange={handleToggleFund}
          aria-label="Эталонная смета — добавить в фонд решений"
        />
      </div>
      {blockedByEmpty && (
        <p className="mt-2 text-xs text-muted-foreground">
          Фонд пополняют решения, принятые оператором при проверке —
          подтвердите или выберите статьи и вернитесь сюда.
        </p>
      )}
```

Серверное «отщёлкивание» + `toast.info` в `handleToggleFund` НЕ трогать — страховка на случай рассинхрона зеркала (спека §4).

- [ ] **Step 6: Тесты зелёные**

Run: `cd frontend; npx vitest run src/pages/estimate/DoneScreen.test.tsx src/lib/reviewState.test.ts` → PASS (все, включая старые).
Run: `cd backend; uv run ruff check .` → чисто (комментарий).

- [ ] **Step 7: Commit**

```bash
git add frontend/src backend/app/services/decision_fund_service.py
git commit -m "feat(fund): promotableCount — зеркало предиката фонда; тумблер disabled с пояснением при 0 решений"
```

---

### Task 9: Логин — инлайн root-ошибка вместо toast

**Files:**
- Modify: `frontend/src/components/auth/LoginScreen.tsx`
- Test: `frontend/src/components/auth/LoginScreen.test.tsx`

- [ ] **Step 1: Переписать тесты ошибок (падающие)**

В `LoginScreen.test.tsx` заменить тесты «на 401 …» и «на другую ошибку …» и добавить тест сброса:

```tsx
  it("на 401 показывает инлайн-ошибку «Неверный логин или пароль», toast НЕ вызывается", async () => {
    vi.spyOn(authApi, "login").mockRejectedValue(new ApiError(401, "bad"))
    renderLogin()
    await userEvent.type(screen.getByLabelText(/логин/i), "a@mr.kz")
    await userEvent.type(screen.getByLabelText(/пароль/i), "x")
    await userEvent.click(screen.getByRole("button", { name: /Войти/ }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Неверный логин или пароль"
    )
    expect(toast.error).not.toHaveBeenCalled()
  })

  it("на другую ошибку — инлайн «Не удалось войти», toast НЕ вызывается", async () => {
    vi.spyOn(authApi, "login").mockRejectedValue(
      new ApiError(500, "server error")
    )
    renderLogin()
    await userEvent.type(screen.getByLabelText(/логин/i), "a@mr.kz")
    await userEvent.type(screen.getByLabelText(/пароль/i), "x")
    await userEvent.click(screen.getByRole("button", { name: /Войти/ }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Не удалось войти/
    )
    expect(toast.error).not.toHaveBeenCalled()
  })

  it("повторный сабмит с верными данными убирает старую root-ошибку", async () => {
    vi.spyOn(authApi, "login")
      .mockRejectedValueOnce(new ApiError(401, "bad"))
      .mockResolvedValueOnce("tok")
    vi.spyOn(authApi, "me").mockResolvedValue({
      id: 1,
      email: "a@mr.kz",
      role: "user",
      is_active: true,
    })
    renderLogin()
    await userEvent.type(screen.getByLabelText(/логин/i), "a@mr.kz")
    await userEvent.type(screen.getByLabelText(/пароль/i), "x")
    await userEvent.click(screen.getByRole("button", { name: /Войти/ }))
    await screen.findByRole("alert")
    await userEvent.click(screen.getByRole("button", { name: /Войти/ }))
    await waitFor(() =>
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    )
  })
```

Тест «успешный вход не показывает toast.error» оставить как есть.

Run: `cd frontend; npx vitest run src/components/auth/LoginScreen.test.tsx` → новые FAIL.

- [ ] **Step 2: LoginScreen — setError("root") + ручной рендер**

Убрать `import { toast } from "sonner"`. `onSubmit`:

```tsx
  async function onSubmit(values: FormValues) {
    // автоочистка root-ошибок в RHF менялась между версиями — сбрасываем явно
    form.clearErrors("root")
    try {
      await login(values.email, values.password)
    } catch (err) {
      const is401 = err instanceof ApiError && err.status === 401
      form.setError("root", {
        message: is401
          ? "Неверный логин или пароль"
          : "Не удалось войти, попробуйте позже",
      })
    }
  }
```

Под кнопкой (после `</Button>`): рендер вручную — shadcn `FormMessage` привязан к полю через `FormField`-контекст и root-ошибку сам не показывает (спека §4):

```tsx
              {form.formState.errors.root?.message && (
                <p className="text-sm text-destructive" role="alert">
                  {form.formState.errors.root.message}
                </p>
              )}
```

- [ ] **Step 3: Тесты зелёные**

Run: `cd frontend; npx vitest run src/components/auth/LoginScreen.test.tsx` → PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/auth
git commit -m "feat(ux): логин — инлайн root-ошибка вместо toast (политика фидбека, ножка 1)"
```

---

### Task 10: Ножки 3–4 — Alert в EstimateList, Skeleton в EstimatePage

**Инвентаризация ножки 4 (спека §4: «места инвентаризирует план»)** — экраны
загрузки данных в приложении и их текущее состояние:

| Поверхность | Сейчас | Действие |
|---|---|---|
| `EstimateList` (список смет) | `Skeleton` уже есть | не трогать |
| `ArticlesPage` (справочник) | `Skeleton` уже есть (`status === "loading"`, строки 100–106) | не трогать |
| `EstimatePage` (`meta.kind === "loading"`) | голый `<p>Загрузка…</p>` | Step 2 ниже |
| `LoginScreen` | не грузит данные асинхронно до сабмита — не применимо | — |
| `AuthGate` (`Загрузка…` — проверка токена при старте SPA) | текстовая заглушка на весь экран, не «область контента с уже видимой структурой» — целиковый préloader SPA, вне табличных/карточных ножки 4 | вне скоупа этапа, не трогать |

Единственный пробел — `EstimatePage`.

**Files:**
- Modify: `frontend/src/components/estimate/EstimateList.tsx` (ошибка загрузки)
- Modify: `frontend/src/pages/estimate/EstimatePage.tsx` (экран «Загрузка…»)

- [ ] **Step 1: EstimateList — ошибка загрузки через Alert**

Импорт: `import { Alert, AlertTitle } from "@/components/ui/alert"`. Блок ошибки (строки 141–147):

```tsx
  if (error) {
    return (
      <Alert variant="destructive" role="alert">
        <AlertTitle>{error}</AlertTitle>
      </Alert>
    )
  }
```

Существующий тест «на ошибке загрузки показывает сообщение» матчит текст — остаётся зелёным.

- [ ] **Step 2: EstimatePage — skeleton вместо текста**

Импорт: `import { Skeleton } from "@/components/ui/skeleton"`. Строка 210:

```tsx
  if (meta.kind === "loading")
    return (
      <div className="space-y-2 p-8" aria-label="Загрузка">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    )
```

- [ ] **Step 3: Тесты зелёные**

Проверено: текущий `EstimatePage.test.tsx` не матчит текст «Загрузка…» ни в одном тесте — замена на `Skeleton` никого не ломает. Если при исполнении окажется, что такой ассерт всё же появился (например, добавлен в Task 12), заменить на проверку `aria-label="Загрузка"`.

Run: `cd frontend; npx vitest run src/components/estimate/EstimateList.test.tsx src/pages/estimate/EstimatePage.test.tsx` → PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src
git commit -m "feat(ux): ошибки загрузки — Alert, процесс загрузки — Skeleton (политика фидбека, ножки 3-4)"
```

---

### Task 11: AppShell — компактный режим

**Files:**
- Modify: `frontend/src/components/AppShell.tsx`
- Test: `frontend/src/components/AppShell.test.tsx`

- [ ] **Step 1: Падающий тест**

В `AppShell.test.tsx` (в файле уже есть `mockAuth()` / `renderShell()` и `USER.email === "a@mr.kz"`) добавить:

```tsx
  it("компактный режим: email скрыт ниже md, иконка-заглушка присутствует", () => {
    mockAuth()
    renderShell("/estimates")
    const email = screen.getByText("a@mr.kz")
    expect(email.className).toContain("hidden")
    expect(email.className).toContain("md:inline")
  })
```

Существующий тест логаута ищет кнопку по имени `/a@mr\.kz/i` — остаётся зелёным: элемент скрывается CSS-классом, jsdom стили не применяет, accessible name сохраняется.

Run: `cd frontend; npx vitest run src/components/AppShell.test.tsx` → FAIL.

- [ ] **Step 2: Реализация**

Импорт иконки: `CircleUser` добавить в импорт из `lucide-react`. Шапка (строка 24):

```tsx
      <header className="flex items-center gap-3 border-b border-[var(--ds-hairline)] bg-[var(--ds-surface-sunken)] px-3 py-3 md:gap-5 md:px-6">
```

Триггер дропдауна (строки 47–50):

```tsx
            <DropdownMenuTrigger className="ml-auto flex items-center gap-1 rounded-sm text-xs text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50">
              <CircleUser className="size-4 md:hidden" />
              <span className="hidden md:inline">{user.email}</span>
              <ChevronDown className="size-3.5" />
            </DropdownMenuTrigger>
```

Высота шапки не меняется (`py-3` как было) — оффсет грида `184px` не затронут (спека §2).

- [ ] **Step 3: Тесты зелёные**

Run: `cd frontend; npx vitest run src/components/AppShell.test.tsx` → PASS (существующие тесты с `getByText(email)` живы — элемент в DOM).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/AppShell.tsx frontend/src/components/AppShell.test.tsx
git commit -m "feat(ux): AppShell — компактный режим ниже md (отступы, email → иконка)"
```

---

### Task 12: Фронтенд — аномалии структуры из GET

**Files:**
- Modify: `frontend/src/lib/api/estimates.ts` (`DetailDto`, `EstimateDetail`, `getEstimate`, общий маппер аномалии)
- Modify: `frontend/src/pages/estimate/EstimatePage.tsx` (notice из GET, удалить `location.state`)
- Modify: `frontend/src/pages/estimate/EstimatesPage.tsx` (navigate без state)
- Modify: `frontend/src/components/estimate/StructureNotice.tsx` (комментарий о транзиентности)
- Test: `frontend/src/lib/api/estimates.test.ts`, `frontend/src/pages/estimate/EstimatePage.test.tsx`, `frontend/src/pages/estimate/EstimatesPage.test.tsx`

**Interfaces:**
- Consumes: поля `anomalies` / `outline_overrides` из `GET /estimates/{id}` (Task 1).
- Produces: `EstimateDetail.anomalies: StructuralAnomaly[]`, `EstimateDetail.outlineOverrides: number`.

- [ ] **Step 1: Падающие тесты маппинга**

В `estimates.test.ts` добавить:

```ts
describe("getEstimate: аномалии структуры (этап 3)", () => {
  it("мапит anomalies и outline_overrides", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue({
      id: 5,
      filename: "a.xlsx",
      status: "ready",
      rows: [],
      anomalies: [
        {
          kind: "duplicate_code",
          source_index: 2,
          code: "1.1",
          name: "B",
          detail: "код встречается 2 раза",
        },
      ],
      outline_overrides: 3,
    })
    const detail = await getEstimate(5)
    expect(detail.anomalies).toEqual([
      {
        kind: "duplicate_code",
        sourceIndex: 2,
        code: "1.1",
        name: "B",
        detail: "код встречается 2 раза",
      },
    ])
    expect(detail.outlineOverrides).toBe(3)
  })

  it("легаси-ответ без полей аномалий → пустые дефолты", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue({
      id: 5,
      filename: "a.xlsx",
      status: "ready",
      rows: [],
    })
    const detail = await getEstimate(5)
    expect(detail.anomalies).toEqual([])
    expect(detail.outlineOverrides).toBe(0)
  })
})
```

Run: `cd frontend; npx vitest run src/lib/api/estimates.test.ts` → FAIL.

- [ ] **Step 2: api/estimates.ts — маппинг**

Вынести DTO-форму аномалии и общий маппер (DRY с `uploadEstimate`):

```ts
interface AnomalyDto {
  kind: string
  source_index: number
  code: string
  name: string
  detail: string
}

function anomalyFromDto(a: AnomalyDto): StructuralAnomaly {
  return {
    kind: a.kind,
    sourceIndex: a.source_index,
    code: a.code,
    name: a.name,
    detail: a.detail,
  }
}
```

`CreateDto.anomalies` перевести на `AnomalyDto[]`, в `uploadEstimate` — `anomalies: (dto.anomalies ?? []).map(anomalyFromDto)`.

`DetailDto` дополнить (опционально-защитно, как соседние поля):

```ts
  // опциональны защитно: старый бэк (до персиста аномалий, этап 3) их не присылал
  anomalies?: AnomalyDto[]
  outline_overrides?: number
```

`EstimateDetail` дополнить:

```ts
  anomalies: StructuralAnomaly[]
  outlineOverrides: number
```

`getEstimate` — в return:

```ts
    anomalies: (dto.anomalies ?? []).map(anomalyFromDto),
    outlineOverrides: dto.outline_overrides ?? 0,
```

Run: `cd frontend; npx vitest run src/lib/api/estimates.test.ts` → PASS.

- [ ] **Step 3: Падающие тесты EstimatePage**

В `EstimatePage.test.tsx`: фикстуру `READY` дополнить `anomalies: [], outlineOverrides: 0` (TS strict теперь требует). Новые тесты:

```tsx
  const DUP_ANOMALY = {
    kind: "duplicate_code",
    sourceIndex: 2,
    code: "1.1",
    name: "B",
    detail: "код встречается 2 раза",
  }

  it("аномалии из GET показываются на экране ревью (прямой заход/F5)", async () => {
    vi.mocked(getEstimate).mockResolvedValue({
      ...READY,
      anomalies: [DUP_ANOMALY],
    })
    renderAt(5)
    expect(
      await screen.findByText(/структура сметы.*1 замечание/i)
    ).toBeInTheDocument()
  })

  it("upload → processing → ready: notice виден после полла (спека §7)", async () => {
    // парсинг синхронен в POST — аномалии уже в первичном GET при status=pending
    vi.mocked(getEstimate).mockResolvedValue({
      ...READY,
      status: "pending",
      rows: [],
      anomalies: [DUP_ANOMALY],
    })
    vi.mocked(pollEstimate).mockResolvedValue({
      fileName: "a.xlsx",
      rows: [ROW_NEEDS_REVIEW],
    })
    renderAt(5)
    expect(
      await screen.findByText(/структура сметы.*1 замечание/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/Выгрузить Excel/)).toBeInTheDocument()
  })
```

Run: `cd frontend; npx vitest run src/pages/estimate/EstimatePage.test.tsx` → новые FAIL.

- [ ] **Step 4: EstimatePage — notice из GET**

Удалить `useLocation` из импорта react-router-dom (и `const location = ...`), удалить чтение `location.state` с комментарием (строки 48–53). Вместо этого:

```tsx
  const [notice, setNotice] = useState<NoticeState>({
    anomalies: [],
    outlineOverrides: 0,
  })
```

В `load()` после `setIsReference(detail.isReference)`:

```tsx
      // аномалии структуры персистятся на бэке и приходят в первичном GET
      // (парсинг синхронен в POST — они в БД до навигации, спека этапа 3 §7);
      // state переживает переход processing→open без ре-фетча
      setNotice({
        anomalies: detail.anomalies,
        outlineOverrides: detail.outlineOverrides,
      })
```

Рендер `<StructureNotice …/>` не меняется (уже берёт из `notice`).

- [ ] **Step 5: EstimatesPage — navigate без state**

```tsx
      const { id } = await uploadEstimate(file)
      navigate(`/estimates/${id}`)
```

В `EstimatesPage.test.tsx` убрать из ассертов ожидание второго аргумента navigate (`{ state: … }`), если есть — оставить проверку пути.

- [ ] **Step 6: StructureNotice — комментарий**

Заменить комментарий о транзиентности (строки 18–20):

```tsx
// Блок «Структура сметы» — справка по результату парсинга. Аномалии
// персистятся на бэке (estimates.structure_anomalies) и приходят в
// GET /estimates/{id} — переживают F5 и прямую ссылку (этап 3 UX).
```

- [ ] **Step 7: Тесты зелёные + typecheck**

Run: `cd frontend; npx vitest run` → PASS весь набор.
Run: `cd frontend; npm run typecheck` → чисто.

- [ ] **Step 8: Commit**

```bash
git add frontend/src
git commit -m "feat(estimates): аномалии структуры из GET — notice переживает F5, navigate-state удалён (этап 3 UX)"
```

---

### Task 13: Финальная верификация и devlog

**Files:**
- Create: `docs/devlog/2026-07-04-ux-stage3-consistency.md`

- [ ] **Step 1: Полный прогон качества**

Run из корня: `just lint` → чисто; `just test` → PASS (pytest + vitest); `cd frontend; npm run typecheck` → чисто; `just build` → сборка ок.

- [ ] **Step 2: Живой гейт (браузер, БЕЗ добавления Playwright в проект — спека §5)**

Поднять `just dev-back` и `just dev-front`, пройти браузерным инструментарием агента (или DevTools) и снять скриншоты:

1. Пять табличных поверхностей — один язык: `/estimates` (список), `/articles` (справочник), грид ревью, полоса контекста в карточке, StructureNotice (смета с дублем кода).
2. Логин с неверным паролем — инлайн-ошибка под кнопкой, без toast.
3. Тумблер фонда на смете без операторских решений — disabled + пояснение.
4. Ширины 960px и ~760px: список, справочник, грид (горизонтальный скролл, шапка не разваливается, колонки не уезжают из-под заголовков), компактная шапка (иконка вместо email). При необходимости скорректировать `min-w-[720px]` в ReviewGrid.
5. F5 на смете с аномалиями — StructureNotice на месте.

- [ ] **Step 3: Devlog**

`docs/devlog/2026-07-04-ux-stage3-consistency.md` — краткий отчёт по формату соседних записей: что сделано (5 направлений этапа), ссылки на спеку/план, результаты гейта (скриншоты — словами), отложенное — ссылкой на TECH_DEBT (магическая высота грида).

- [ ] **Step 4: Commit**

```bash
git add docs/devlog
git commit -m "docs: devlog этапа 3 UX — консистентность и демо-лоск"
```

---

## Self-Review Checklist (заполняется автором плана)

- Спека §3 (табличный язык) → Task 4–7; §4 (фидбек) → Task 8–10 + логин Task 9; §5 (адаптив) → Task 6 (overflow), 7 (min-w), 11 (шапка), 13 (гейт); §6 (плюрализация) → Task 2–3; §7 (персист аномалий) → Task 1, 12; §8 (тесты) → распределены по задачам; §9 (вне скоупа) → TECH_DEBT в Task 7.
