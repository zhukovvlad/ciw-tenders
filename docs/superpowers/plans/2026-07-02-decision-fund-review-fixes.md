# Ревью-фиксы золотого фонда (PR #17) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** закрыть дефекты глубокого ревью PR #17 (фонд решений): потеря фонд-строк в экспорте,
CardinalityViolation на промоушене, неисправимость отравленного фонда, накрутка votes, молчаливый
отскок тумблера — плюс продуктовое изменение формата экспорта «(код) Название».

**Architecture:** точечные фиксы поверх утверждённого дизайна фонда с амендментами спеки
([2026-06-30-decision-fund-design.md §12](../specs/2026-06-30-decision-fund-design.md)) и матрицы
экспорта SP3 ([2026-06-23-estimate-review-export-sp3-design.md §5](../specs/2026-06-23-estimate-review-export-sp3-design.md)).
Clean Architecture не меняется; порт `EstimateRepository` получает bulk-метод `save_fund_hits`.

**Tech Stack:** FastAPI + SQLAlchemy (sync Session) + pgvector/Neon; React + TS + vitest; pytest + фейки портов.

## Global Constraints

- Бэкенд строго через `uv run` из `backend/` (`.venv`); кириллица в stdout → `PYTHONIOENCODING=utf-8`.
- ruff line-length 100, `from __future__ import annotations`, type hints обязательны.
- Юнит-тесты НЕ ходят в реальную БД/AI — фейки портов (`tests/fakes.py`); интеграционные тесты
  фонда гейтятся `TEST_DATABASE_URL` (отдельный Neon-эндпоинт).
- Фронт: prettier `printWidth 80`, `npm run typecheck` = `tsc -b`; shadcn-компоненты в
  `src/components/ui/` не править.
- Направление зависимостей: `api → services → domain ← infrastructure`.
- Коммиты — по задаче; переводы строк LF.

---

### Task 1: Экспорт — matched_fund в матрице + формат «(код) Название» ✅ ВЫПОЛНЕНО

**Files:**
- Modify: `backend/app/services/estimate_export_service.py` (`_cell_value` + новый `_format_article`)
- Test: `backend/tests/test_estimate_export_service.py`, `backend/tests/test_estimate_export.py`

**Сделано (в working tree):** `_cell_value` отдаёт `_format_article(final_code, final_name)` для
confirmed/overridden и `_format_article(matched_code, matched_name)` для `unreviewed + (confident |
matched_fund)`; `_format_article(code, name)` → `"(код) Название"`, без имени — голый код, без кода —
пусто. Тесты: 4 новых юнита (RED→GREEN), обновлён golden-раунд-трип `test_export_writes_final_code_to_node_physrow`
(`"ИТ-9"` → `"(ИТ-9) Выбрано"`).

- [x] RED: `uv run pytest tests/test_estimate_export_service.py -q` — 3 falls
- [x] GREEN: `10 passed` (оба файла)
- [x] **Commit:** `git add backend/app/services/estimate_export_service.py backend/tests/test_estimate_export_service.py backend/tests/test_estimate_export.py docs/superpowers/specs/2026-06-23-estimate-review-export-sp3-design.md; git commit -m "fix(export): matched_fund в матрице значений + формат «(код) Название» (амендмент SP3 §5)"`

---

### Task 2: Дедуп FundEntry в promote() — фикс CardinalityViolation ✅ ВЫПОЛНЕНО

**Files:**
- Modify: `backend/app/services/decision_fund_service.py` (promote: дедуп по conflict-ключу)
- Modify: `backend/tests/fakes.py` (`FakeDecisionFundRepository.upsert` честен по дублям — `ValueError`
  на повтор conflict-ключа в одном батче, зеркало Postgres CardinalityViolation)
- Test: `backend/tests/test_decision_fund_service.py::test_promote_dedupes_repeated_rows_in_one_batch`

**Сделано:** `promote()` собирает записи в `dict` по ключу `(cache_key_hash, CRUMB_DERIVATION_VERSION,
final_article_id)` (`setdefault` — первая строка побеждает), `entries = list(by_key.values())`.

- [x] RED: честный фейк + новый тест → `ValueError: duplicate conflict key`
- [x] GREEN: `uv run pytest tests/test_decision_fund_service.py -q` — 4 passed
- [x] **Commit:** `git add backend/app/services/decision_fund_service.py backend/tests/fakes.py backend/tests/test_decision_fund_service.py; git commit -m "fix(fund): дедуп conflict-ключа в promote() — CardinalityViolation на повторяющихся строках"`

---

### Task 3: Votes — повторный промоушен того же источника не накручивает ✅ ВЫПОЛНЕНО

**Files:**
- Modify: `backend/app/infrastructure/db/decision_fund_repository.py` (upsert: `votes = CASE WHEN
  source_estimate_id = excluded.source_estimate_id THEN votes ELSE votes + 1 END`; заодно один `ins`
  вместо тройного `pg_insert(...)`)
- Test: `backend/tests/test_decision_fund_repository_integration.py::test_upsert_same_source_does_not_inflate_votes`

- [x] RED: интеграционный тест (реальный тест-Postgres) → votes==2
- [x] GREEN: `uv run pytest tests/test_decision_fund_repository_integration.py -q` — 4 passed
  (включая старый `..._increments_votes_and_updates_source`: другой источник по-прежнему +1)
- [x] **Commit:** `git add backend/app/infrastructure/db/decision_fund_repository.py backend/tests/test_decision_fund_repository_integration.py; git commit -m "fix(fund): votes не инфлируется повторным промоушеном того же источника (спека §12.5)"`

---

### Task 4: statusLabel учитывает решение оператора

**Files:**
- Modify: `frontend/src/lib/reviewState.ts:157-162` (`statusLabel`)
- Test: `frontend/src/lib/reviewState.test.ts`

**Interfaces:**
- Produces: `statusLabel(row, d)` — порядок веток: `no_match` → `pending` → `manual` →
  `matched_fund` → «Подтверждено оператором». Task 5 (ReviewRow) рендерит иконку фонда по
  `label === "Из фонда"`.

- [x] **Step 1: RED — тесты на решение поверх фонда**

В `frontend/src/lib/reviewState.test.ts` (хелпер `fundRow()` уже есть):

```ts
it("statusLabel: нетронутый фонд-хит → «Из фонда», override → «Ручной выбор», reject → «Нет совпадения»", () => {
  const row = fundRow()
  expect(
    statusLabel(row, { kind: "confirmed", code: "a", name: "b", manual: false })
  ).toBe("Из фонда")
  expect(
    statusLabel(row, { kind: "confirmed", code: "a", name: "b", manual: true })
  ).toBe("Ручной выбор")
  expect(statusLabel(row, { kind: "no_match" })).toBe("Нет совпадения")
})
```

- [x] **Step 2: Run** `cd frontend && npx vitest run src/lib/reviewState.test.ts` — Expected: FAIL
  (`manual:true` и `no_match` дают «Из фонда»)
- [x] **Step 3: GREEN — переупорядочить ветки**

```ts
export function statusLabel(row: MatchRow, d: Decision): string {
  if (d.kind === "no_match") return "Нет совпадения"
  if (d.kind === "pending") return "Требует проверки"
  if (d.manual) return "Ручной выбор"
  if (row.status === "matched_fund") return "Из фонда"
  return "Подтверждено оператором"
}
```

- [x] **Step 4: Run** тот же vitest — Expected: PASS (все тесты файла)
- [x] **Step 5: Commit** `git add frontend/src/lib/reviewState.ts frontend/src/lib/reviewState.test.ts; git commit -m "fix(front): statusLabel уважает решение оператора поверх matched_fund (спека §12.4)"`

---

### Task 5: ReviewRow — фонд-хит раскрывается и переопределяется

**Files:**
- Modify: `frontend/src/pages/estimate/ReviewRow.tsx`
- Test: `frontend/src/pages/estimate/ReviewRow.test.tsx`

**Interfaces:**
- Consumes: `requiresDecision`, `statusLabel` из `@/lib/reviewState` (Task 4).
- Produces: строка `matched_fund` кликабельна (onToggle) и в раскрытом виде даёт ручной поиск →
  `onManualPick` → существующий `handleReview(..., "pick", id)` (PATCH override; бэкенд принимает —
  ревью-сервис блокирует только `status='pending'`).

- [x] **Step 1: RED — тесты кликабельности и поиска**

В `ReviewRow.test.tsx` (фикстура `fundRow` уже есть; передавать реалистичное решение
`{ kind: "confirmed", code: ..., name: ..., manual: false }` — после Task 4 label зависит от решения):

```tsx
const fundDecision = {
  kind: "confirmed" as const,
  code: fundRow.matched_code!,
  name: fundRow.matched_name!,
  manual: false,
}

it("фонд-строка кликабельна: клик зовёт onToggle (переопределение доступно)", async () => {
  const onToggle = vi.fn()
  render(
    tableWrap(
      <ReviewRow
        row={fundRow}
        decision={fundDecision}
        expanded={false}
        onToggle={onToggle}
        onPickCandidate={vi.fn()}
        onManualPick={vi.fn()}
        onConfirmNoMatch={vi.fn()}
      />
    )
  )
  await userEvent.click(screen.getByText(/из фонда/i))
  expect(onToggle).toHaveBeenCalled()
})

it("раскрытая фонд-строка даёт ручной поиск по справочнику (override)", () => {
  render(
    tableWrap(
      <ReviewRow
        row={fundRow}
        decision={fundDecision}
        expanded
        onToggle={vi.fn()}
        onPickCandidate={vi.fn()}
        onManualPick={vi.fn()}
        onConfirmNoMatch={vi.fn()}
      />
    )
  )
  expect(
    screen.getByPlaceholderText(/искать в справочнике/i)
  ).toBeInTheDocument()
})
```

И обновить первый тест файла («бейдж из фонда»): `decision={{ kind: "pending" }}` →
`decision={fundDecision}` (после Task 4 pending-решение даёт «Требует проверки»).

- [x] **Step 2: Run** `npx vitest run src/pages/estimate/ReviewRow.test.tsx` — Expected: FAIL
  (onToggle не вызван; поиска нет — строка не раскрывается)
- [x] **Step 3: GREEN — развести flagged (требует внимания) и expandable (можно раскрыть)**

В `ReviewRow.tsx`:

```tsx
import { requiresDecision, statusLabel } from "@/lib/reviewState"
// ...
const flagged = requiresDecision(row) // warning-рамка: только реально спорные
// фонд-хит не требует решения, но должен быть переопределяем (спека фонда §12.4)
const expandable = flagged || row.status === "matched_fund"
const label = statusLabel(row, decision)
```

- `<tr className={...}>`: `expandable ? "cursor-pointer" + (flagged ? " border-l-2 border-l-[var(--warning)]" : "") : ""`
- `onClick={expandable ? onToggle : undefined}`
- шеврон: `{expandable && (<ChevronDown ... />)}`
- панель: `{expanded && expandable && (...)}` (кандидатов у фонд-строки нет — `candidates=[]`,
  рендерится только ручной поиск; этого достаточно для override)
- иконка фонда и текст статуса: `{label === "Из фонда" && (<Database ... />)}{label}`

- [x] **Step 4: Run** тот же vitest — Expected: PASS (все тесты файла)
- [x] **Step 5: Commit** `git add frontend/src/pages/estimate/ReviewRow.tsx frontend/src/pages/estimate/ReviewRow.test.tsx; git commit -m "fix(front): фонд-хит переопределяем — строка раскрывается, ручной поиск доступен (спека §12.4)"`

---

### Task 6: Ре-матчинг переразрешает unreviewed matched_fund (бэкенд)

**Files:**
- Modify: `backend/app/infrastructure/db/estimate_repository.py:342-365` (`save_node_classifications`)
- Modify: `backend/tests/fakes.py:594-602` (`FakeEstimateRepository.save_node_classifications`)
- Test: `backend/tests/test_estimate_matching_service.py`

**Interfaces:**
- Produces: гард классификации сбрасывает `matched_fund` в `pending` **только при
  `review_status='unreviewed'`**; ревью-статусы неприкосновенны. После сброса строка в том же
  прогоне переразрешается `_apply_fund` (фонд жив → тот же снимок) или уходит в RAG (запись снята).

- [x] **Step 1: RED — фейк-тесты гарда + сервисный тест восстановления**

В `test_estimate_matching_service.py` (секция Task 7 fake_repo):

```python
def test_fake_repo_reclassify_resets_unreviewed_matched_fund() -> None:
    # отравленный фонд лечится: ре-прогон возвращает нетронутый фонд-хит в pending (спека §12.3)
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "x")
    repo.nodes[nid]["status"] = "matched_fund"
    repo.save_node_classifications([NodeClassification(nid, excluded=False, embedding_input="x")])
    assert repo.get(1, 1, is_admin=True).rows[0].status == "pending"


def test_fake_repo_reclassify_keeps_reviewed_matched_fund() -> None:
    # решение человека поверх фонд-хита неприкосновенно
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "x")
    repo.nodes[nid]["status"] = "matched_fund"
    repo.nodes[nid]["review_status"] = "confirmed"
    repo.save_node_classifications([NodeClassification(nid, excluded=False, embedding_input="x")])
    assert repo.get(1, 1, is_admin=True).rows[0].status == "matched_fund"


def test_rematch_after_fund_cleanup_reresolves_row() -> None:
    # строка проштампована фондом → запись фонда сняли → повторный полный прогон даёт RAG-результат
    repo = FakeEstimateRepository()
    fund = FakeDecisionFundRepository()
    est = repo.create(NewEstimate(1, "f.xlsx", "k"),
                      [EstimateNode("1.1.5", "МОКАП", "1.1", None, "МОКАП", 0, 3)])
    key = cache_key_hash(normalize_cache_key("МОКАП"))
    fund.seed_hit(key, CRUMB_DERIVATION_VERSION, FundHit(5, "1.4", "Мокап"))
    art = _ready_articles([ArticleCandidate(_article(9, "1.99"), 0.97)])
    svc = _matching_service(repo, art, fund, apply_fund=True)
    svc.match_estimate(est.id)
    assert repo.get(est.id, 1, is_admin=True).rows[0].status == "matched_fund"
    fund.clear()  # плохую запись сняли (unreference + rebuild)
    svc.match_estimate(est.id)
    row = repo.get(est.id, 1, is_admin=True).rows[0]
    assert row.status == "confident" and row.matched_article_id == 9  # переразрешено RAG-ом
```

- [x] **Step 2: Run** `uv run pytest tests/test_estimate_matching_service.py -q` — Expected: FAIL
  (сброса нет — строка остаётся matched_fund со старой статьёй)
- [x] **Step 3: GREEN — расширить гард (SQL + фейк зеркально)**

`estimate_repository.py` (в `save_node_classifications`, `or_`/`and_` импортировать из sqlalchemy):

```python
.where(
    EstimateRowModel.id == r.node_id,
    or_(
        EstimateRowModel.status.in_(("pending", "excluded", "error", "no_match")),
        # спека фонда §12.3: нетронутый фонд-хит переразрешается на ре-прогоне
        # (лечение отравленного фонда); ревью-статусы неприкосновенны
        and_(
            EstimateRowModel.status == "matched_fund",
            EstimateRowModel.review_status == "unreviewed",
        ),
    ),
)
```

`fakes.py`:

```python
resettable = n["status"] in ("pending", "excluded", "error", "no_match") or (
    n["status"] == "matched_fund" and n["review_status"] == "unreviewed"
)
if not resettable:
    continue  # охрана: терминальные матч/ревью-статусы неприкосновенны
```

Обновить комментарий-охрану в обоих местах (упомянуть §12.3) и добавить у гарда однострочник
(ревью плана): «сброс не чистит matched_* — снимок перезапишется дальше по пайплайну
(_apply_fund/_match_values); при краше между classify-commit и фонд-пассом pending временно
несёт stale-снимок до следующего ре-прогона» — чтобы будущий читатель не удивлялся
`pending` с `matched_article_id`.

- [x] **Step 4: Run** `uv run pytest tests/test_estimate_matching_service.py tests/test_estimate_fund_methods.py -q` — Expected: PASS
- [x] **Step 5: Commit** `git add backend/app/infrastructure/db/estimate_repository.py backend/tests/fakes.py backend/tests/test_estimate_matching_service.py; git commit -m "fix(matching): ре-прогон переразрешает unreviewed matched_fund — лечение отравленного фонда (спека §12.3)"`

---

### Task 7: DoneScreen — подсказка при promoted=0

**Files:**
- Modify: `frontend/src/pages/estimate/DoneScreen.tsx:40-42`
- Test: `frontend/src/pages/estimate/DoneScreen.test.tsx`

- [x] **Step 1: RED — тест подсказки** (замокать sonner на уровне файла):

```tsx
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn() } }))
import { toast } from "sonner"

it("promoted=0 при включении → подсказка, почему тумблер отщёлкнулся", async () => {
  vi.mocked(setReference).mockResolvedValueOnce({
    is_reference: false,
    promoted: 0,
  })
  render(
    <DoneScreen
      state={initReview("смета.xlsx", MOCK_ROWS)}
      onExport={vi.fn()}
      onNewEstimate={vi.fn()}
      estimateId={1}
    />
  )
  await userEvent.click(screen.getByRole("switch"))
  await vi.waitFor(() => {
    expect(toast.info).toHaveBeenCalled()
  })
})
```

- [x] **Step 2: Run** `npx vitest run src/pages/estimate/DoneScreen.test.tsx` — Expected: FAIL
  (toast.info не вызывается)
- [x] **Step 3: GREEN — читать promoted в then-ветке**

```ts
.then((r) => {
  if (seq !== toggleSeq.current) return
  setInFund(r.is_reference)
  if (next && !r.is_reference && r.promoted === 0) {
    // бэк не ставит is_reference при 0 промоученных строк (см. toggle_reference) — объясняем
    toast.info(
      "Смета не добавлена в фонд: нет подтверждённых решений. " +
        "Подтвердите или выберите статьи на шаге проверки и включите тумблер снова."
    )
  }
})
```

- [x] **Step 4: Run** тот же vitest — Expected: PASS (все тесты файла, включая latest-wins)
- [x] **Step 5: Commit** `git add frontend/src/pages/estimate/DoneScreen.tsx frontend/src/pages/estimate/DoneScreen.test.tsx; git commit -m "fix(front): DoneScreen объясняет отщёлкивание тумблера при promoted=0"`

---

### Task 8: Bulk save_fund_hits — один commit на фонд-пасс

**Files:**
- Modify: `backend/app/domain/decision_fund.py` (+`AppliedFundHit`)
- Modify: `backend/app/domain/ports.py` (`save_fund_hit` → `save_fund_hits`)
- Modify: `backend/app/infrastructure/db/estimate_repository.py:406-415`
- Modify: `backend/tests/fakes.py:639-649`
- Modify: `backend/app/services/estimate_matching_service.py:204-221` (`_apply_fund`)
- Test: `backend/tests/test_estimate_fund_methods.py`

**Interfaces:**
- Produces: `AppliedFundHit(row_id: int, article_id: int, code: str, name: str)` (frozen dataclass,
  domain/decision_fund.py); порт `save_fund_hits(hits: Sequence[AppliedFundHit]) -> None` —
  CAS по `review_status='unreviewed'` на каждую строку, **один commit на батч**. Старый
  `save_fund_hit` удаляется (нет мёртвого кода).

- [x] **Step 1: RED — переписать тесты fund-методов на bulk**

В `test_estimate_fund_methods.py` заменить оба `save_fund_hit`-теста:

```python
from app.domain.decision_fund import AppliedFundHit

def test_save_fund_hits_writes_snapshot_bulk() -> None:
    repo = FakeEstimateRepository()
    eid = seed_estimate_with_rows(
        repo,
        [
            Row(embedding_input="к. лист", status="pending", review_status="unreviewed"),
            Row(embedding_input="к. лист 2", status="pending", review_status="unreviewed"),
        ],
    )
    ids = sorted(n["id"] for n in repo.nodes.values() if n["estimate_id"] == eid)
    repo.save_fund_hits([
        AppliedFundHit(ids[0], article_id=5, code="1.4", name="Мокап"),
        AppliedFundHit(ids[1], article_id=7, code="1.5", name="Иное"),
    ])
    assert [repo.nodes[i]["status"] for i in ids] == ["matched_fund", "matched_fund"]
    assert repo.nodes[ids[0]]["matched_article_id"] == 5
    assert repo.nodes[ids[1]]["matched_code"] == "1.5"
    assert repo.nodes[ids[0]]["score"] is None and repo.nodes[ids[0]]["candidates"] == []


def test_save_fund_hits_cas_skips_reviewed() -> None:
    repo = FakeEstimateRepository()
    eid = seed_estimate_with_rows(
        repo, [Row(embedding_input="x", status="pending", review_status="confirmed")]
    )
    rid = next(n["id"] for n in repo.nodes.values() if n["estimate_id"] == eid)
    repo.save_fund_hits([AppliedFundHit(rid, article_id=5, code="1.4", name="Мокап")])
    assert repo.nodes[rid]["status"] != "matched_fund"  # CAS по unreviewed
```

- [x] **Step 2: Run** `uv run pytest tests/test_estimate_fund_methods.py -q` — Expected: FAIL
  (`AppliedFundHit`/`save_fund_hits` не существуют)
- [x] **Step 3: GREEN — домен, порт, SQL, фейк, сервис**

`domain/decision_fund.py`:

```python
@dataclass(frozen=True, slots=True)
class AppliedFundHit:
    """Решённый фонд-хит для bulk-записи снимков в строки сметы (один commit на пасс)."""

    row_id: int
    article_id: int
    code: str
    name: str
```

`domain/ports.py` (вместо `save_fund_hit`; импорт `AppliedFundHit`):

```python
@abstractmethod
def save_fund_hits(self, hits: Sequence[AppliedFundHit]) -> None:
    """Снимки фонд-хитов (status='matched_fund'), CAS по review_status='unreviewed';
    один commit на батч (зеркало save_node_classifications)."""
```

`estimate_repository.py` (вместо `save_fund_hit`):

```python
def save_fund_hits(self, hits: Sequence[AppliedFundHit]) -> None:
    # CAS по unreviewed — как save_node_match; candidates/score обнуляем (снимок без кандидатов).
    # Один commit на весь фонд-пасс (зеркало save_node_classifications): N commits → 1
    # (fsync + атомарность пасса); UPDATE-ы по-прежнему поштучные.
    for h in hits:
        self._session.execute(
            update(EstimateRowModel)
            .where(
                EstimateRowModel.id == h.row_id,
                EstimateRowModel.review_status == "unreviewed",
            )
            .values(status="matched_fund", matched_article_id=h.article_id,
                    matched_code=h.code, matched_name=h.name, candidates=None, score=None,
                    match_error=None)
        )
    self._session.commit()
```

`fakes.py` — зеркально (цикл по hits, тот же CAS, всё в памяти).

`estimate_matching_service.py::_apply_fund` — копить и писать одним вызовом:

```python
applied: list[AppliedFundHit] = []
for n in nodes:
    candidates = found.get(by_hash[n.row_id], [])
    decision = resolve_fund_decision([h.article_id for h in candidates])
    if decision is None:
        continue  # промах/конфликт → остаётся pending → RAG
    hit = next(h for h in candidates if h.article_id == decision)
    applied.append(AppliedFundHit(n.row_id, hit.article_id, hit.code, hit.name))
if applied:
    self._estimates.save_fund_hits(applied)
return len(applied)
```

(импорт `AppliedFundHit` из `app.domain.decision_fund`).

- [x] **Step 4: Run** `uv run pytest tests/test_estimate_fund_methods.py tests/test_estimate_matching_service.py tests/test_decision_fund_service.py -q` — Expected: PASS; `git grep -n save_fund_hit -- backend` → только `save_fund_hits`
- [x] **Step 5: Commit** `git add backend/app/domain/decision_fund.py backend/app/domain/ports.py backend/app/infrastructure/db/estimate_repository.py backend/tests/fakes.py backend/app/services/estimate_matching_service.py backend/tests/test_estimate_fund_methods.py; git commit -m "perf(fund): bulk save_fund_hits — один commit на фонд-пасс вместо per-row round-trip"`

---

### Task 9: _apply_fund до _embed_nodes — фонд-хиты не эмбеддятся

**Files:**
- Modify: `backend/app/services/estimate_matching_service.py:74-90` (порядок стадий)
- Modify: `backend/app/infrastructure/db/estimate_repository.py:204-221` (`fetch_unembedded_nodes`)
- Modify: `backend/tests/fakes.py:495-512` (зеркало фильтра)
- Test: `backend/tests/test_estimate_matching_service.py`

**Interfaces:**
- Produces: порядок `classify → _apply_fund → _embed_nodes → gate → _match_nodes` (спека §12.2);
  `fetch_unembedded_nodes` исключает `excluded` И `matched_fund`. Гейт остаётся ПОСЛЕ embed
  (тест `test_blocked_when_dictionary_empty_raises` фиксирует «embed не впустую»).

- [x] **Step 1: RED — тест «хит не эмбеддится»**

Расширить `_matching_service` параметром `embedder=None` (`embedder=embedder or _Embedder()`), затем:

```python
def test_fund_hit_rows_are_not_embedded() -> None:
    # экономия эмбеддинга — суть кэша (спека §12.2): хит закрывается ДО _embed_nodes
    repo, fund = FakeEstimateRepository(), FakeDecisionFundRepository()
    est = repo.create(NewEstimate(1, "f.xlsx", "k"), [
        EstimateNode("1.1", "МОКАП", "1", None, "МОКАП", 0, 2),
        EstimateNode("1.2", "Кровля", "1", None, "Кровля", 1, 2),
    ])
    fund.seed_hit(cache_key_hash(normalize_cache_key("МОКАП")),
                  CRUMB_DERIVATION_VERSION, FundHit(5, "1.4", "Мокап"))
    art = _ready_articles([ArticleCandidate(_article(9, "1.99"), 0.97)])
    embedder = _Embedder()
    svc = _matching_service(repo, art, fund, apply_fund=True, embedder=embedder)
    svc.match_estimate(est.id)
    embedded = [t for batch in embedder.batches for t in batch]
    assert "МОКАП" not in embedded          # фонд-хит не оплачивал эмбеддинг
    assert "Кровля" in embedded             # промах пошёл штатно
    rows = {r.embedding_input: r for r in repo.get(est.id, 1, is_admin=True).rows}
    assert rows["МОКАП"].status == "matched_fund"
    assert rows["Кровля"].status == "confident"
```

- [x] **Step 2: Run** `uv run pytest tests/test_estimate_matching_service.py::test_fund_hit_rows_are_not_embedded -q` — Expected: FAIL («МОКАП» в embedded)
- [x] **Step 3: GREEN — переставить стадию + сузить фильтр**

`match_estimate`:

```python
excluded = self._classify_nodes(estimate_id)
logger.debug("Матчинг %s: классификация завершена (ORG-исключено: %d)", estimate_id, excluded)
fund_hits = self._apply_fund(estimate_id)  # ДО эмбеддинга: хиту вектор не нужен (спека §12.2)
self._embed_nodes(estimate_id)  # только промахи фонда (fetch_unembedded исключает matched_fund)
logger.debug("Матчинг %s: эмбеддинг завершён", estimate_id)
# гейт каталога — только если после фонда остались не-фондовые matchable (pending). ...
```

`estimate_repository.py::fetch_unembedded_nodes`: `EstimateRowModel.status != "excluded"` →
`EstimateRowModel.status.notin_(("excluded", "matched_fund"))`. Фейк: `n["status"] not in ("excluded", "matched_fund")`.

- [x] **Step 4: Run** `uv run pytest tests/test_estimate_matching_service.py -q` — Expected: PASS
  (в т.ч. `test_blocked_when_dictionary_empty_raises` — embed по-прежнему до гейта)
- [x] **Step 5: Commit** `git add backend/app/services/estimate_matching_service.py backend/app/infrastructure/db/estimate_repository.py backend/tests/fakes.py backend/tests/test_estimate_matching_service.py; git commit -m "perf(matching): _apply_fund до _embed_nodes — фонд-хиты не оплачивают эмбеддинг (спека §12.2)"`

---

### Task 10: Мелочи ревью (ABC, кросс-ссылки версии, лёгкий exists, CLAUDE.md)

**Files:**
- Modify: `backend/app/infrastructure/db/decision_fund_repository.py:15`
- Modify: `backend/app/domain/classification.py` (комментарий у `CRUMB_DERIVATION_VERSION`)
- Modify: `backend/app/domain/decision_fund.py` (докстринг `normalize_cache_key`)
- Modify: `backend/app/domain/ports.py`, `backend/app/infrastructure/db/estimate_repository.py`,
  `backend/tests/fakes.py` (+`exists`), `backend/app/api/routes/estimates.py:169-184`
- Modify: `CLAUDE.md`
- Test: `backend/tests/test_estimate_routes.py` (toggle-тесты не меняются — маршрут сохраняет контракт)

- [x] **Step 1: ABC** — `class SqlAlchemyDecisionFundRepository(DecisionFundRepository):`
  (+ `from app.domain.ports import DecisionFundRepository`), как остальные шесть адаптеров.
- [x] **Step 2: Кросс-ссылки версии ключа.** У `CRUMB_DERIVATION_VERSION` (classification.py) добавить
  в комментарий: «Также бампаем при изменении `normalize_cache_key` (domain/decision_fund.py) — ключи
  фонда хэшируются поверх неё». В докстринг `normalize_cache_key`: «Меняешь нормализацию → бампай
  `CRUMB_DERIVATION_VERSION` (domain/classification.py), иначе весь фонд молча остынет».
- [x] **Step 3: Лёгкая проверка владения.** Порт: `exists(estimate_id, requester_id, *, is_admin) -> bool`;
  SQL — `session.get(EstimateModel, ...)` + проверка владельца (зеркало `delete`/`get_object_key`,
  без загрузки строк с векторами); фейк — по `self.estimates`. В `toggle_reference` заменить
  `repository.get(...) is None` на `not repository.exists(...)`.

```python
# ports.py
@abstractmethod
def exists(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> bool:
    """Существует и доступна запрашивающему (без загрузки строк/векторов)."""

# estimate_repository.py
def exists(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> bool:
    est = self._session.get(EstimateModel, estimate_id)
    return est is not None and (is_admin or est.user_id == requester_id)

# routes/estimates.py::toggle_reference
if not repository.exists(estimate_id, user.id or 0, is_admin=user.role is Role.ADMIN):
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Смета не найдена")
```

- [x] **Step 4: CLAUDE.md.** Строку «Сметы нигде не хранятся…» дополнить: персистентны справочник
  (`template_articles`), сметы (`estimates`/`estimate_rows`) и фонд решений (`decision_fund`).
  В правило «Сопоставление: …» добавить стадию: «перед RAG — exact-match фонд решений
  (`_apply_fund`, статус `matched_fund`); см. `decision_fund_service.py`».
- [x] **Step 5: Run** `uv run pytest tests/test_estimate_routes.py -q` — Expected: PASS (контракт
  роутов не изменился); `uv run ruff check .` — чисто.
- [x] **Step 6: Commit** `git add -A backend/app CLAUDE.md backend/tests/fakes.py; git commit -m "chore(fund): ABC-порт адаптера, кросс-ссылки версии ключа, лёгкий exists в toggle, актуализация CLAUDE.md"`

---

### Task 11: Финальная верификация + devlog

- [x] **Step 1:** `just lint` — ruff + eslint + prettier чисты
- [x] **Step 2:** `just test` — pytest + vitest зелёные. Интеграционные тесты фонда гоняются
  только при `TEST_DATABASE_URL` (backend/.env, тест-эндпоинт Neon) — проверить в сводке pytest,
  что `test_decision_fund_repository_integration.py` НЕ в статусе skipped (иначе строка devlog
  «интеграционные зелёные» — враньё).
  **Факт:** бэкенд 362 passed / 3 skipped (прежние lock/sweep-гейты), интеграционные фонда —
  4 PASSED; vitest 124 passed; tsc/eslint/prettier чисты.
- [x] **Step 3:** `cd frontend && npm run typecheck` — чисто
- [x] **Step 4:** devlog `docs/devlog/2026-07-02-decision-fund-review-fixes.md`: что нашло ревью
  (10 подтверждённых пунктов), что изменили в спеках (§12 фонда, амендмент SP3 §5), остаточные
  компромиссы (votes при чередовании смет — v1; типизированные Out-схемы тумблера — TECH_DEBT).
- [x] **Step 5:** запись в `docs/TECH_DEBT.md`: response_model/Out-схемы для `toggle_reference` и
  `rebuild_fund`; `Depends(require_admin)` как guard-only dependency.
- [x] **Step 6: Commit** `git add docs; git commit -m "docs: спека-амендменты §12 + план + devlog ревью-фиксов фонда"`

---

## Self-Review

- **Покрытие ревью:** все 10 финальных находок закрыты задачами (1→экспорт, 2→дедуп, 3→votes,
  4-5→UI override+label, 6→ре-матчинг, 7→promoted=0, 8→bulk-запись, 9→порядок стадий, 10→мелочи+CLAUDE.md);
  находки «Out-схемы» и «редундантный индекс» осознанно в TECH_DEBT (Task 11), индекс не трогаем —
  прежнее ревью PR #17 явно требовало синхронный ORM-индекс, спор не заводим без замера.
- **Типы согласованы:** `AppliedFundHit` определён в Task 8 и используется там же (сервис+порт+SQL+фейк);
  `exists` определён и потреблён в Task 10; `requiresDecision`/`statusLabel` из Task 4 потребляются в Task 5.
- **Плейсхолдеров нет:** каждый код-шаг несёт конкретный код; команды с ожидаемым исходом.
