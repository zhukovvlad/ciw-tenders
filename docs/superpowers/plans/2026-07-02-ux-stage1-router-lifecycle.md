# Этап 1 UX-роадмапа: роутер и жизненный цикл сметы — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** URL-адресуемые сметы (react-router) с честным маппингом статус→экран через серверное `completed_at`, пагинация списка смет с видимым прогрессом ревью, удаление sessionStorage-кэша ревью и `beforeunload`-guard.

**Architecture:** Бэк получает поле `estimates.completed_at` + эндпоинт `PATCH /estimates/{id}/completion`, список смет — `limit/offset` + агрегаты прогресса ревью (FILTER-подзапрос). Фронт переезжает с конечного автомата фаз в `EstimateFlow` на роуты `/estimates`, `/estimates/:id`, `/articles`; фаза выводится из ответа `GET /estimates/{id}` (status + completed_at). Источник истины — сервер; sessionStorage-кэш ревью удаляется.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (бэк), react-router-dom v7 (library mode), shadcn/ui, vitest + RTL, pytest + фейки портов.

**Спека:** `docs/superpowers/specs/2026-07-02-ux-roadmap-design.md` §3 (+§2 таблица решений).

## Global Constraints

- Бэкенд: только `uv run` (никакого системного python/pip); ruff line-length 100, `from __future__ import annotations`, type hints обязательны.
- Юнит-тесты бэка НЕ ходят в реальную БД/AI: фейки портов (`backend/tests/fakes.py`) + `app.dependency_overrides`.
- Направление зависимостей: `api → services → domain ← infrastructure`; новая возможность внешнего слоя — сначала порт в `domain/ports.py`.
- Фронт: shadcn-first — новый UI из shadcn-примитивов (`src/components/ui/` — вендорные, не править); импорты через `@/`; TypeScript strict, `erasableSyntaxOnly` (без enum/parameter properties); Prettier `printWidth 80`, LF.
- `npm run typecheck` = `tsc -b` (не `tsc --noEmit`).
- Windows PowerShell 5.1: в командах `;` вместо `&&`; кириллица в stdout Python → `PYTHONIOENCODING=utf-8`.
- Бэкенд-порт 8260. Секреты только в `backend/.env`.
- Коммиты частые, после каждой зелёной задачи.

## Верификация всего этапа (после последней задачи)

`just lint` → 0 ошибок; `just test` → все зелёные; `cd frontend; npm run typecheck` → 0 ошибок; `just migrate` применён на dev-БД.

---

### Task 1: Бэк — `completed_at`: миграция, ORM, домен, DTO

**Files:**
- Create: `backend/alembic/versions/0008_estimate_completed_at.py`
- Modify: `backend/app/infrastructure/db/models.py` (EstimateModel, ~строка 91)
- Modify: `backend/app/domain/entities.py` (Estimate ~240, EstimateSummary ~254)
- Modify: `backend/app/infrastructure/db/estimate_repository.py` (`_to_entity`, `list_for_owner` маппинг)
- Modify: `backend/app/api/schemas.py` (EstimateDetailOut ~199, EstimateSummaryOut ~133)
- Test: `backend/tests/test_estimate_completion.py` (новый)

**Interfaces:**
- Produces: `Estimate.completed_at: datetime | None`, `EstimateSummary.completed_at: datetime | None`, `EstimateDetailOut.completed_at`, `EstimateSummaryOut.completed_at` — используются задачами 2–4.

- [ ] **Step 1: Написать падающий тест на DTO-маппинг**

Создать `backend/tests/test_estimate_completion.py`:

```python
"""Тесты жизненного цикла завершения сметы (этап 1 UX-роадмапа)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.api.schemas import EstimateDetailOut, EstimateSummaryOut
from app.domain.entities import Estimate, EstimateSummary

_TS = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)


def test_detail_out_carries_completed_at() -> None:
    est = Estimate(
        id=1, user_id=1, filename="a.xlsx", status="ready",
        created_at=_TS, completed_at=_TS,
    )
    out = EstimateDetailOut.from_entity(est)
    assert out.completed_at == _TS


def test_detail_out_completed_at_defaults_none() -> None:
    est = Estimate(id=1, user_id=1, filename="a.xlsx", status="ready", created_at=_TS)
    assert EstimateDetailOut.from_entity(est).completed_at is None


def test_summary_out_carries_completed_at() -> None:
    s = EstimateSummary(
        id=1, filename="a.xlsx", status="ready", nodes_count=3,
        created_at=_TS, completed_at=_TS,
    )
    assert EstimateSummaryOut.from_entity(s).completed_at == _TS
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest tests/test_estimate_completion.py -v`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'completed_at'`.

- [ ] **Step 3: Домен + ORM + DTO**

`entities.py` — в `Estimate` (после `is_reference`) и `EstimateSummary` (после `created_at`) добавить:

```python
    completed_at: datetime | None = None  # оператор закрыл ревью (этап 1 UX); None = открыта
```

`models.py`, `EstimateModel` — после `is_reference`:

```python
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

`schemas.py`: `EstimateDetailOut` и `EstimateSummaryOut` — поле `completed_at: datetime | None = None` и проброс в обоих `from_entity` (`completed_at=e.completed_at` / `completed_at=s.completed_at`).

`estimate_repository.py`: в `_to_entity` и в конструкторе `EstimateSummary` внутри `list_for_owner` добавить `completed_at=m.completed_at`.

- [ ] **Step 4: Тест зелёный + ничего не сломано**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest tests/test_estimate_completion.py tests/test_estimate_routes.py tests/test_estimate_repository_mapping.py -v`
Expected: PASS.

- [ ] **Step 5: Миграция**

Создать `backend/alembic/versions/0008_estimate_completed_at.py` (сверить `down_revision` c фактическим `revision` в `0007_decision_fund.py`):

```python
"""estimates.completed_at — оператор закрыл ревью (этап 1 UX-роадмапа)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "estimates",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("estimates", "completed_at")
```

- [ ] **Step 6: Применить миграцию**

Run: `just migrate`
Expected: `Running upgrade 0007 -> 0008`.

- [ ] **Step 7: Commit**

```bash
git add backend/alembic/versions/0008_estimate_completed_at.py backend/app/infrastructure/db/models.py backend/app/domain/entities.py backend/app/infrastructure/db/estimate_repository.py backend/app/api/schemas.py backend/tests/test_estimate_completion.py
git commit -m "feat(estimates): поле completed_at — серверное состояние завершения ревью"
```

---

### Task 2: Бэк — эндпоинт завершения/возобновления

**Files:**
- Modify: `backend/app/domain/ports.py` (EstimateRepository, рядом с `list_for_owner` ~181)
- Modify: `backend/app/domain/errors.py` (новая ошибка)
- Modify: `backend/app/infrastructure/db/estimate_repository.py`
- Modify: `backend/app/services/estimate_service.py`
- Modify: `backend/app/api/schemas.py` (CompletionToggleIn/Out)
- Modify: `backend/app/api/routes/estimates.py`
- Modify: `backend/tests/fakes.py` (FakeEstimateRepository)
- Test: `backend/tests/test_estimate_completion.py` (дополнить)

**Interfaces:**
- Consumes: `Estimate.completed_at` (Task 1).
- Produces: порт `EstimateRepository.set_completed(estimate_id: int, requester_id: int, *, is_admin: bool, completed: bool) -> tuple[str, datetime | None] | None` (None = не найдена/чужая; иначе `(status, completed_at)`); `EstimateService.set_completed(...) -> datetime | None` (LookupError → 404, EstimateNotCompletableError → 409); роут `PATCH /estimates/{estimate_id}/completion` c телом `{"completed": bool}` и ответом `{"completed_at": datetime | null}`. Используется фронтом (Task 4, 7).

- [ ] **Step 1: Падающие тесты сервиса**

Дополнить `test_estimate_completion.py` (фейк расширяется в Step 3; `_make_service`/`_stored_estimate` — по образцу хелперов в `tests/test_estimate_service.py`, свериться с его фикстурами):

```python
import pytest

from app.domain.errors import EstimateNotCompletableError
from tests.fakes import FakeEstimateRepository


def _service_with_ready_estimate() -> tuple:
    """EstimateService + смета в статусе ready (см. паттерн test_estimate_service.py)."""
    repo = FakeEstimateRepository()
    est = _seed_estimate(repo, status="ready")  # хелпер: создать смету через repo.create + set_status
    service = _make_estimate_service(repo)
    return service, est


def test_complete_sets_timestamp() -> None:
    service, est = _service_with_ready_estimate()
    ts = service.set_completed(est.id, 1, is_admin=False, completed=True)
    assert ts is not None


def test_reopen_clears_timestamp() -> None:
    service, est = _service_with_ready_estimate()
    service.set_completed(est.id, 1, is_admin=False, completed=True)
    ts = service.set_completed(est.id, 1, is_admin=False, completed=False)
    assert ts is None


def test_complete_running_estimate_rejected() -> None:
    service, est = _service_with_running_estimate()  # status="running"
    with pytest.raises(EstimateNotCompletableError):
        service.set_completed(est.id, 1, is_admin=False, completed=True)


def test_complete_unknown_estimate_raises_lookup() -> None:
    service, _ = _service_with_ready_estimate()
    with pytest.raises(LookupError):
        service.set_completed(9999, 1, is_admin=False, completed=True)


def test_complete_foreign_estimate_raises_lookup_for_non_admin() -> None:
    service, est = _service_with_ready_estimate()  # владелец user_id=1
    with pytest.raises(LookupError):
        service.set_completed(est.id, 2, is_admin=False, completed=True)
```

- [ ] **Step 2: Убедиться, что падают**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest tests/test_estimate_completion.py -v`
Expected: FAIL — `ImportError: EstimateNotCompletableError` / `AttributeError: set_completed`.

- [ ] **Step 3: Реализация**

`domain/errors.py`:

```python
class EstimateNotCompletableError(Exception):
    """Завершить можно только смету в терминально-успешном статусе (ready/partial_error)."""
```

`domain/ports.py`, в `EstimateRepository`:

```python
    @abstractmethod
    def set_completed(
        self, estimate_id: int, requester_id: int, *, is_admin: bool, completed: bool
    ) -> tuple[str, datetime | None] | None:
        """Выставить/снять completed_at. None — не найдена/чужая.
        Возвращает (status, completed_at) после записи. Идемпотентен."""
        ...
```

`infrastructure/db/estimate_repository.py`:

```python
    _COMPLETABLE = ("ready", "partial_error")

    def set_completed(
        self, estimate_id: int, requester_id: int, *, is_admin: bool, completed: bool
    ) -> tuple[str, datetime | None] | None:
        est = self._session.get(EstimateModel, estimate_id)
        if est is None or (not is_admin and est.user_id != requester_id):
            return None
        if completed and est.status not in self._COMPLETABLE:
            raise EstimateNotCompletableError(
                f"Смета в статусе '{est.status}' не может быть завершена"
            )
        est.completed_at = datetime.now(UTC) if completed else None
        self._session.commit()
        return est.status, est.completed_at
```

(импорты: `from datetime import UTC, datetime`; `from app.domain.errors import EstimateNotCompletableError`.)

`services/estimate_service.py`:

```python
    def set_completed(
        self, estimate_id: int, requester_id: int, *, is_admin: bool, completed: bool
    ) -> datetime | None:
        res = self._repository.set_completed(
            estimate_id, requester_id, is_admin=is_admin, completed=completed
        )
        if res is None:
            raise LookupError("Смета не найдена")
        _, completed_at = res
        return completed_at
```

`tests/fakes.py`, `FakeEstimateRepository` (стиль соседних методов; хранить в `self.completed: dict[int, datetime | None]`):

```python
    def set_completed(
        self, estimate_id: int, requester_id: int, *, is_admin: bool, completed: bool
    ) -> tuple[str, datetime | None] | None:
        est = self.estimates.get(estimate_id)
        if est is None or (not is_admin and est.user_id != requester_id):
            return None
        status = self.statuses.get(estimate_id, est.status)
        if completed and status not in ("ready", "partial_error"):
            raise EstimateNotCompletableError(f"Смета в статусе '{status}' не может быть завершена")
        self.completed[estimate_id] = datetime.now(UTC) if completed else None
        return status, self.completed[estimate_id]
```

- [ ] **Step 4: Тесты сервиса зелёные**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest tests/test_estimate_completion.py -v`
Expected: PASS.

- [ ] **Step 5: Падающий тест роута**

Дополнить `test_estimate_completion.py` роут-тестами по образцу фикстур `tests/test_estimate_routes.py` (клиент с `dependency_overrides` для `get_estimate_service`/`get_current_user`):

```python
def test_patch_completion_route_ok(client_with_ready_estimate) -> None:
    client, est_id = client_with_ready_estimate
    resp = client.patch(f"/estimates/{est_id}/completion", json={"completed": True})
    assert resp.status_code == 200
    assert resp.json()["completed_at"] is not None


def test_patch_completion_route_conflict_for_running(client_with_running_estimate) -> None:
    client, est_id = client_with_running_estimate
    resp = client.patch(f"/estimates/{est_id}/completion", json={"completed": True})
    assert resp.status_code == 409


def test_patch_completion_route_404(client_with_ready_estimate) -> None:
    client, _ = client_with_ready_estimate
    resp = client.patch("/estimates/9999/completion", json={"completed": True})
    assert resp.status_code == 404
```

Run: то же — Expected: FAIL 404/405 (роута нет).

- [ ] **Step 6: Роут + DTO**

`api/schemas.py`:

```python
class CompletionToggleIn(BaseModel):
    completed: bool


class CompletionOut(BaseModel):
    completed_at: datetime | None
```

`api/routes/estimates.py` (импортировать `CompletionToggleIn`, `CompletionOut`, `EstimateNotCompletableError`):

```python
@router.patch("/{estimate_id}/completion", response_model=CompletionOut)
def toggle_completion(
    estimate_id: int,
    body: CompletionToggleIn,
    user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> CompletionOut:
    try:
        completed_at = service.set_completed(
            estimate_id, user.id or 0, is_admin=user.role is Role.ADMIN,
            completed=body.completed,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except EstimateNotCompletableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return CompletionOut(completed_at=completed_at)
```

- [ ] **Step 7: Все тесты бэка зелёные**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest -q; uv run ruff check .`
Expected: PASS, 0 ошибок ruff.

- [ ] **Step 8: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat(estimates): PATCH /completion — завершение/возобновление ревью (владелец/админ)"
```

---

### Task 3: Бэк — пагинация списка смет + прогресс ревью

**Files:**
- Modify: `backend/app/domain/entities.py` (EstimateSummary)
- Modify: `backend/app/domain/ports.py` (`list_for_owner` сигнатура)
- Modify: `backend/app/infrastructure/db/estimate_repository.py:115-140`
- Modify: `backend/app/services/estimate_service.py` (`list`)
- Modify: `backend/app/api/schemas.py` (EstimateSummaryOut, новый EstimateListOut)
- Modify: `backend/app/api/routes/estimates.py:115-122`
- Modify: `backend/tests/fakes.py`
- Test: `backend/tests/test_estimate_list_progress.py` (новый)

**Interfaces:**
- Produces: `EstimateSummary` дополнен `reviewed_count: int = 0`, `total_reviewable: int = 0`; порт `list_for_owner(owner_id, *, is_admin, limit: int = 50, offset: int = 0) -> tuple[list[EstimateSummary], int]` (второй элемент — общее число смет владельца); `GET /estimates?limit=&offset=` → `{"items": [...], "total": int}` (**ломающее изменение формы ответа** — фронт чинится в Task 4). Семантика прогресса зеркалит фронтовый `progress()`: reviewable = строки со status ∈ {needs_review, no_match, error}; reviewed = из них с review_status ≠ 'unreviewed'.

- [ ] **Step 1: Падающие тесты**

`backend/tests/test_estimate_list_progress.py` — сеять через `FakeEstimateRepository`-паттерны нельзя (агрегаты — SQL), поэтому тестируем на уровне роута с фейком, который возвращает уже подсчитанные саммари, + отдельный юнит на форму ответа:

```python
"""Пагинация GET /estimates и счётчики прогресса (этап 1 UX-роадмапа)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.api.schemas import EstimateListOut, EstimateSummaryOut
from app.domain.entities import EstimateSummary

_TS = datetime(2026, 7, 2, tzinfo=UTC)


def test_summary_out_carries_progress() -> None:
    s = EstimateSummary(
        id=1, filename="a.xlsx", status="ready", nodes_count=10,
        created_at=_TS, reviewed_count=4, total_reviewable=7,
    )
    out = EstimateSummaryOut.from_entity(s)
    assert (out.reviewed_count, out.total_reviewable) == (4, 7)


def test_list_route_paginates(client_with_three_estimates) -> None:
    client = client_with_three_estimates
    resp = client.get("/estimates", params={"limit": 2, "offset": 0})
    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_list_route_default_shape(client_with_three_estimates) -> None:
    body = client_with_three_estimates.get("/estimates").json()
    assert set(body.keys()) == {"items", "total"}
```

Плюс интеграционный тест SQL-агрегатов — в стиле `tests/test_decision_fund_repository_integration.py` (если в проекте есть маркер интеграции с реальной БД — использовать его; иначе пропустить SQL-тест и проверить агрегаты вручную через Step 6):

```python
# test: смета с 5 строками — 2 confident, 2 needs_review (одна confirmed), 1 excluded
# ожидание: total_reviewable=2, reviewed_count=1, nodes_count=4 (excluded не считается)
```

- [ ] **Step 2: Убедиться, что падают**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest tests/test_estimate_list_progress.py -v`
Expected: FAIL (нет полей/EstimateListOut).

- [ ] **Step 3: Реализация**

`entities.py`, `EstimateSummary` — после `completed_at`:

```python
    reviewed_count: int = 0        # решённые из требующих решения (зеркало фронтового progress())
    total_reviewable: int = 0      # строки status ∈ (needs_review, no_match, error)
```

`ports.py`:

```python
    @abstractmethod
    def list_for_owner(
        self, owner_id: int, *, is_admin: bool, limit: int = 50, offset: int = 0
    ) -> tuple[list[EstimateSummary], int]:
        """Страница смет владельца (админ — все) + общее число. Сортировка: created_at DESC."""
        ...
```

`infrastructure/db/estimate_repository.py` — заменить `list_for_owner` (строки 115–140):

```python
    _REVIEWABLE = ("needs_review", "no_match", "error")

    def list_for_owner(
        self, owner_id: int, *, is_admin: bool, limit: int = 50, offset: int = 0
    ) -> tuple[list[EstimateSummary], int]:
        counts = (
            select(
                EstimateRowModel.estimate_id,
                func.count()
                .filter(EstimateRowModel.status != "excluded")
                .label("n"),
                func.count()
                .filter(EstimateRowModel.status.in_(self._REVIEWABLE))
                .label("reviewable"),
                func.count()
                .filter(
                    EstimateRowModel.status.in_(self._REVIEWABLE),
                    EstimateRowModel.review_status != "unreviewed",
                )
                .label("reviewed"),
            )
            .group_by(EstimateRowModel.estimate_id)
            .subquery()
        )
        stmt = select(
            EstimateModel,
            func.coalesce(counts.c.n, 0),
            func.coalesce(counts.c.reviewable, 0),
            func.coalesce(counts.c.reviewed, 0),
        ).outerjoin(counts, counts.c.estimate_id == EstimateModel.id)
        total_stmt = select(func.count()).select_from(EstimateModel)
        if not is_admin:
            stmt = stmt.where(EstimateModel.user_id == owner_id)
            total_stmt = total_stmt.where(EstimateModel.user_id == owner_id)
        stmt = stmt.order_by(EstimateModel.created_at.desc()).limit(limit).offset(offset)
        total = self._session.execute(total_stmt).scalar_one()
        return [
            EstimateSummary(
                id=m.id,
                filename=m.filename,
                status=m.status,
                nodes_count=n,
                created_at=m.created_at,
                completed_at=m.completed_at,
                reviewed_count=reviewed,
                total_reviewable=reviewable,
            )
            for m, n, reviewable, reviewed in self._session.execute(stmt)
        ], total
```

`services/estimate_service.py`:

```python
    def list(
        self, owner_id: int, *, is_admin: bool, limit: int = 50, offset: int = 0
    ) -> tuple[list[EstimateSummary], int]:
        return self._repository.list_for_owner(
            owner_id, is_admin=is_admin, limit=limit, offset=offset
        )
```

`api/schemas.py`: в `EstimateSummaryOut` — `reviewed_count: int = 0`, `total_reviewable: int = 0` (+ проброс в `from_entity`); новый:

```python
class EstimateListOut(BaseModel):
    items: list[EstimateSummaryOut]
    total: int
```

`api/routes/estimates.py`:

```python
@router.get("", response_model=EstimateListOut)
def list_estimates(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> EstimateListOut:
    is_admin = user.role is Role.ADMIN
    items, total = service.list(user.id or 0, is_admin=is_admin, limit=limit, offset=offset)
    return EstimateListOut(
        items=[EstimateSummaryOut.from_entity(s) for s in items], total=total
    )
```

`tests/fakes.py` — привести `FakeEstimateRepository.list_for_owner` к новой сигнатуре (сортировка + срез + total; счётчики по `self.nodes`).

- [ ] **Step 4: Всё зелёное**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest -q; uv run ruff check .`
Expected: PASS (включая старые тесты списка — обновить их ожидания на `{"items","total"}`, если они проверяли голый массив).

- [ ] **Step 5: Ручная проверка SQL-агрегатов на живой dev-БД**

Run: `just dev-back` + `curl -s -H "Authorization: Bearer <токен>" "http://localhost:8260/api/estimates?limit=5"` (токен — логином под админом).
Expected: `items[].reviewed_count/total_reviewable` соответствуют данным (2 сметы в dev-БД).

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat(estimates): пагинация списка + счётчики прогресса ревью (reviewed/total)"
```

---

### Task 4: Фронт — api-слой: detail/completion/list

**Files:**
- Modify: `frontend/src/lib/api/estimates.ts`
- Test: `frontend/src/lib/api/estimates.test.ts` (дополнить в стиле существующих тестов файла)

**Interfaces:**
- Consumes: контракты Task 2–3.
- Produces (используются Task 5–8):
  - `getEstimate(id): Promise<EstimateDetail>` где `EstimateDetail = { id: number; fileName: string; status: string; statusDetail: string | null; completedAt: string | null; isReference: boolean; rows: MatchRow[] }`
  - `setCompletion(id: number, completed: boolean): Promise<{ completedAt: string | null }>`
  - `listEstimates(opts?: { limit?: number; offset?: number }): Promise<{ items: EstimateListItem[]; total: number }>`
  - `EstimateListItem` дополнен `completedAt: string | null`, `reviewedCount: number`, `totalReviewable: number`.

- [ ] **Step 1: Падающие тесты**

Дополнить `estimates.test.ts` (мокинг — тем же способом, каким файл мокает `apiGet`/`apiSend` сейчас; свериться с его началом):

```ts
it("getEstimate возвращает status и completedAt", async () => {
  mockApiGet({
    id: 5, filename: "a.xlsx", status: "ready", status_detail: null,
    completed_at: "2026-07-02T12:00:00Z", is_reference: false, rows: [],
  })
  const d = await getEstimate(5)
  expect(d.status).toBe("ready")
  expect(d.completedAt).toBe("2026-07-02T12:00:00Z")
})

it("setCompletion шлёт PATCH /completion", async () => {
  mockApiSend({ completed_at: null })
  const r = await setCompletion(5, false)
  expect(r.completedAt).toBeNull()
  expectLastSend("PATCH", "/estimates/5/completion", { completed: false })
})

it("listEstimates отдаёт items+total и прокидывает limit/offset", async () => {
  mockApiGet({
    items: [{
      id: 1, filename: "a.xlsx", status: "ready", nodes_count: 3,
      created_at: "2026-07-01T00:00:00Z", completed_at: null,
      reviewed_count: 1, total_reviewable: 2,
    }],
    total: 7,
  })
  const r = await listEstimates({ limit: 10, offset: 20 })
  expect(r.total).toBe(7)
  expect(r.items[0].reviewedCount).toBe(1)
})
```

- [ ] **Step 2: Убедиться, что падают**

Run: `cd frontend; npx vitest run src/lib/api/estimates.test.ts`
Expected: FAIL.

- [ ] **Step 3: Реализация**

В `estimates.ts`:

```ts
export interface EstimateDetail {
  id: number
  fileName: string
  status: string
  statusDetail: string | null
  completedAt: string | null // ISO
  isReference: boolean
  rows: MatchRow[]
}

export async function getEstimate(id: number): Promise<EstimateDetail> {
  const dto = await apiGet<DetailDto>(`/estimates/${id}`)
  return {
    id: dto.id,
    fileName: dto.filename,
    status: dto.status,
    statusDetail: dto.status_detail ?? null,
    completedAt: dto.completed_at ?? null,
    isReference: dto.is_reference ?? false,
    rows: dto.rows.map(rowFromDto),
  }
}

export async function setCompletion(
  id: number,
  completed: boolean
): Promise<{ completedAt: string | null }> {
  const dto = await apiSend<{ completed_at: string | null }>(
    "PATCH",
    `/estimates/${id}/completion`,
    { completed }
  )
  return { completedAt: dto.completed_at }
}

export interface EstimateListItem {
  id: number
  filename: string
  status: string
  nodesCount: number
  createdAt: string // ISO — форматируется в UI
  completedAt: string | null
  reviewedCount: number
  totalReviewable: number
}

export async function listEstimates(opts?: {
  limit?: number
  offset?: number
}): Promise<{ items: EstimateListItem[]; total: number }> {
  const limit = opts?.limit ?? 50
  const offset = opts?.offset ?? 0
  const dto = await apiGet<{ items: SummaryDto[]; total: number }>(
    `/estimates?limit=${limit}&offset=${offset}`
  )
  return {
    items: dto.items.map((d) => ({
      id: d.id,
      filename: d.filename,
      status: d.status,
      nodesCount: d.nodes_count,
      createdAt: d.created_at,
      completedAt: d.completed_at ?? null,
      reviewedCount: d.reviewed_count ?? 0,
      totalReviewable: d.total_reviewable ?? 0,
    })),
    total: dto.total,
  }
}
```

(`DetailDto`/`SummaryDto` дополнить полями `status_detail?`, `completed_at?`, `reviewed_count?`, `total_reviewable?`. Вызовы `getEstimate` в `DoneScreen`/`EstimateFlow` совместимы — поле `isReference` осталось.)

- [ ] **Step 4: Зелёные тесты + typecheck**

Run: `cd frontend; npx vitest run src/lib/api; npm run typecheck`
Expected: PASS. (Компилятор укажет места, где `listEstimates()` звали без аргументов и ждали массив — `EstimateList.tsx`; починить временно `const { items } = await listEstimates()` — полноценная пагинация в Task 8.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(api): detail с completed_at, setCompletion, пагинированный listEstimates"
```

---

### Task 5: Фронт — роутер и AppShell

**Files:**
- Modify: `frontend/package.json` (react-router-dom)
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Test: `frontend/src/App.test.tsx`, `frontend/src/components/AppShell.test.tsx` (обновить)

**Interfaces:**
- Produces: роуты `/estimates` (элемент `EstimatesPage`, Task 6), `/estimates/:id` (`EstimatePage`, Task 7), `/articles`; `AppShell` без пропсов `tab`/`onTab` (нав-состояние из `useLocation`). До Task 6/7 в роуты временно ставится существующий `EstimateFlow` (страницы заменят его).

- [ ] **Step 1: Установить роутер**

Run: `cd frontend; npm install react-router-dom`
Expected: `react-router-dom@^7` в dependencies.

- [ ] **Step 2: Падающий тест навигации**

`AppShell.test.tsx` — обновить рендер на `MemoryRouter` и добавить:

```tsx
it("таб «Справочник» ведёт на /articles", async () => {
  render(
    <MemoryRouter initialEntries={["/estimates"]}>
      <Routes>
        <Route element={<AppShell><Outlet /></AppShell>}>
          <Route path="/estimates" element={<div>estimates-page</div>} />
          <Route path="/articles" element={<div>articles-page</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
  await userEvent.click(screen.getByRole("tab", { name: /Справочник/ }))
  expect(screen.getByText("articles-page")).toBeInTheDocument()
})

it("бренд — ссылка на /estimates", () => {
  /* рендер как выше на /articles; клик по «MR · Сметы» → estimates-page */
})
```

Run: `cd frontend; npx vitest run src/components/AppShell.test.tsx` — Expected: FAIL.

- [ ] **Step 3: AppShell на useLocation/useNavigate**

`AppShell.tsx`: убрать пропсы `tab`/`onTab` и импорт `clearReview` (кэш удаляется в Task 7 полностью); children оставить:

```tsx
import { Link, useLocation, useNavigate } from "react-router-dom"

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, role, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const tab = location.pathname.startsWith("/articles") ? "articles" : "estimate"
  return (
    <div className="min-h-svh bg-background">
      <header className="...как сейчас...">
        <Link to="/estimates" className="font-display text-base">
          MR <span className="text-[var(--ds-accent-hover)]">·</span> Сметы
        </Link>
        <Tabs
          value={tab}
          onValueChange={(v) =>
            navigate(v === "articles" ? "/articles" : "/estimates")
          }
        >
          {/* TabsList/TabsTrigger — без изменений */}
        </Tabs>
        {/* DropdownMenu — без изменений, но onSelect={() => logout()} */}
      </header>
      <main>{children}</main>
    </div>
  )
}
```

- [ ] **Step 4: App.tsx на Routes**

```tsx
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

export function App() {
  return (
    <AuthProvider>
      <AuthGate>
        <BrowserRouter>
          <AppShell>
            <Routes>
              <Route path="/" element={<Navigate to="/estimates" replace />} />
              <Route path="/estimates" element={<EstimateFlow />} />
              <Route path="/articles" element={<ArticlesPage />} />
              <Route path="*" element={<Navigate to="/estimates" replace />} />
            </Routes>
          </AppShell>
        </BrowserRouter>
      </AuthGate>
      <Toaster />
    </AuthProvider>
  )
}
```

(`/estimates/:id` появится в Task 7; `EstimateFlow` пока живёт на `/estimates`.)

- [ ] **Step 5: Обновить App.test.tsx (обёртки роутера) и прогнать всё**

Run: `cd frontend; npx vitest run; npm run typecheck`
Expected: PASS (тесты, рендерившие `AppShell` с пропсами `tab`/`onTab`, — обновить).

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(router): react-router — /estimates и /articles, AppShell с NavLink-табами"
```

---

### Task 6: Фронт — EstimatesPage: загрузка → переход на /estimates/:id

**Files:**
- Create: `frontend/src/pages/estimate/EstimatesPage.tsx`
- Modify: `frontend/src/App.tsx` (роут `/estimates`)
- Test: `frontend/src/pages/estimate/EstimatesPage.test.tsx` (новый; перенос сценариев из `StartProcessing.test.tsx`)

**Interfaces:**
- Consumes: `uploadEstimate` (существующий), `StartScreen` (существующий), роутер Task 5.
- Produces: страница `/estimates`; после успешного upload — `navigate(`/estimates/${id}`, { state: { anomalies, outlineOverrides } })`. Location-state читает Task 7.

- [ ] **Step 1: Падающий тест**

```tsx
// EstimatesPage.test.tsx — vi.mock("@/lib/api/estimates")
it("после загрузки файла уходит на /estimates/:id с аномалиями в state", async () => {
  vi.mocked(uploadEstimate).mockResolvedValue({
    id: 42, anomalies: [], outlineOverrides: 0,
  })
  render(
    <MemoryRouter initialEntries={["/estimates"]}>
      <Routes>
        <Route path="/estimates" element={<EstimatesPage />} />
        <Route path="/estimates/:id" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>
  )
  const input = screen.getByLabelText(/файл сметы/)
  await userEvent.upload(input, new File(["x"], "смета.xlsx"))
  expect(await screen.findByTestId("probe-path")).toHaveTextContent("/estimates/42")
})
```

(`LocationProbe` — маленький локальный компонент теста, печатающий `useLocation().pathname` в `data-testid="probe-path"`.)

Run: `cd frontend; npx vitest run src/pages/estimate/EstimatesPage.test.tsx` — Expected: FAIL.

- [ ] **Step 2: Реализация**

```tsx
// frontend/src/pages/estimate/EstimatesPage.tsx
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { uploadEstimate } from "@/lib/api/estimates"
import type { EstimateListItem } from "@/lib/api/estimates"
import { StartScreen } from "@/pages/estimate/StartScreen"
import { ProcessingScreen } from "@/pages/estimate/ProcessingScreen"

export function EstimatesPage() {
  const navigate = useNavigate()
  const [uploadingName, setUploadingName] = useState<string | null>(null)

  async function handleFile(file: File) {
    setUploadingName(file.name)
    try {
      const { id, anomalies, outlineOverrides } = await uploadEstimate(file)
      navigate(`/estimates/${id}`, { state: { anomalies, outlineOverrides } })
    } catch (err) {
      console.error(err)
      toast.error(
        err instanceof Error ? err.message : "Не удалось загрузить смету"
      )
      setUploadingName(null)
    }
  }

  if (uploadingName !== null)
    return (
      <ProcessingScreen
        fileName={uploadingName}
        progress={{ phase: "parsing", done: 0, total: 0, etaSeconds: null }}
      />
    )
  return (
    <StartScreen
      onFile={handleFile}
      onOpen={(item: EstimateListItem) => navigate(`/estimates/${item.id}`)}
    />
  )
}
```

`App.tsx`: `/estimates` → `<EstimatesPage />`.

- [ ] **Step 3: Зелёные тесты**

Run: `cd frontend; npx vitest run src/pages/estimate; npm run typecheck`
Expected: PASS (кроме `EstimateFlow.test.tsx` — он умрёт в Task 7; если ломается уже сейчас, пометить `describe.skip` с комментарием `// удаляется в Task 7`).

- [ ] **Step 4: Commit**

```bash
git add frontend/src
git commit -m "feat(estimates): страница /estimates — загрузка ведёт на /estimates/:id"
```

---

### Task 7: Фронт — EstimatePage: URL→фаза, завершение, удаление кэша

**Files:**
- Create: `frontend/src/pages/estimate/EstimatePage.tsx`
- Modify: `frontend/src/App.tsx` (роут `/estimates/:id`)
- Modify: `frontend/src/pages/estimate/ReviewScreen.tsx` (шапка: «Ко всем сметам», «Завершить» с AlertDialog; проп `onNewEstimate` → `onComplete`)
- Modify: `frontend/src/pages/estimate/DoneScreen.tsx` (проп `onResume`; ссылка на `/estimates` вместо `onNewEstimate`)
- Delete: `frontend/src/pages/estimate/EstimateFlow.tsx`, `frontend/src/pages/estimate/EstimateFlow.test.tsx`, `frontend/src/lib/session.ts`, `frontend/src/lib/session.test.ts`
- Test: `frontend/src/pages/estimate/EstimatePage.test.tsx` (новый), обновить `ReviewScreen.test.tsx`, `DoneScreen.test.tsx`

**Interfaces:**
- Consumes: `getEstimate`/`setCompletion`/`pollEstimate`/`patchRowReview` (Task 4), reducer `reviewState` (без изменений), location-state Task 6.
- Produces: страница `/estimates/:id` — единственный владелец фазовой логики. Маппинг (спека §3): `pending|running` → ProcessingScreen+poll; `ready|partial_error` + `completedAt === null` → ReviewScreen; + `completedAt !== null` → DoneScreen; `blocked` → Alert destructive со `statusDetail` и ссылкой на `/estimates`. Новые пропсы: `ReviewScreen.onComplete: () => void`, `DoneScreen.onResume: () => void`.

- [ ] **Step 1: Падающие тесты маппинга URL→фаза**

```tsx
// EstimatePage.test.tsx — vi.mock("@/lib/api/estimates")
function renderAt(id: number) {
  return render(
    <MemoryRouter initialEntries={[`/estimates/${id}`]}>
      <Routes>
        <Route path="/estimates/:id" element={<EstimatePage />} />
        <Route path="/estimates" element={<div>list-page</div>} />
      </Routes>
    </MemoryRouter>
  )
}

const READY = {
  id: 5, fileName: "a.xlsx", status: "ready", statusDetail: null,
  completedAt: null, isReference: false, rows: [ROW_NEEDS_REVIEW],
}

it("ready без completedAt → экран ревью", async () => {
  vi.mocked(getEstimate).mockResolvedValue(READY)
  renderAt(5)
  expect(await screen.findByText(/Выгрузить Excel/)).toBeInTheDocument()
})

it("ready с completedAt → итоговый экран", async () => {
  vi.mocked(getEstimate).mockResolvedValue({
    ...READY, completedAt: "2026-07-02T12:00:00Z",
  })
  renderAt(5)
  expect(await screen.findByText(/Возобновить проверку/)).toBeInTheDocument()
})

it("blocked → сообщение об отказе и ссылка к списку", async () => {
  vi.mocked(getEstimate).mockResolvedValue({
    ...READY, status: "blocked", statusDetail: "нет строк СМР", rows: [],
  })
  renderAt(5)
  expect(await screen.findByRole("alert")).toHaveTextContent("нет строк СМР")
})

it("«Завершить» дергает setCompletion и показывает итог", async () => {
  vi.mocked(getEstimate).mockResolvedValue(READY)
  vi.mocked(setCompletion).mockResolvedValue({ completedAt: "2026-07-02T12:00:00Z" })
  renderAt(5)
  await userEvent.click(await screen.findByRole("button", { name: /Завершить/ }))
  // строка нерешённая → AlertDialog «осталось N спорных»
  await userEvent.click(screen.getByRole("button", { name: /Завершить всё равно/ }))
  expect(await screen.findByText(/Возобновить проверку/)).toBeInTheDocument()
  expect(setCompletion).toHaveBeenCalledWith(5, true)
})
```

(`ROW_NEEDS_REVIEW` — взять образец `MatchRow` из фикстур `@/lib/mock/fixtures`, как делают соседние тесты.)

Run: `cd frontend; npx vitest run src/pages/estimate/EstimatePage.test.tsx` — Expected: FAIL (модуля нет).

- [ ] **Step 2: EstimatePage**

```tsx
// frontend/src/pages/estimate/EstimatePage.tsx
// Единственный владелец маппинга статус→экран (спека §3). Кэша ревью нет:
// источник истины — GET /estimates/:id + ответы PATCH.
import { useCallback, useEffect, useReducer, useState } from "react"
import { Link, useLocation, useParams } from "react-router-dom"
import { toast } from "sonner"
import type { Progress } from "@/lib/mock/api"
import type { StructuralAnomaly } from "@/lib/types"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { StructureNotice } from "@/components/estimate/StructureNotice"
import { initReview, reviewReducer } from "@/lib/reviewState"
import type { ReviewActionKind } from "@/pages/estimate/ReviewScreen"
import {
  exportEstimate,
  getEstimate,
  patchRowReview,
  pollEstimate,
  setCompletion,
} from "@/lib/api/estimates"
import { ProcessingScreen } from "@/pages/estimate/ProcessingScreen"
import { ReviewScreen } from "@/pages/estimate/ReviewScreen"
import { DoneScreen } from "@/pages/estimate/DoneScreen"

interface NoticeState {
  anomalies: StructuralAnomaly[]
  outlineOverrides: number
}

type Meta =
  | { kind: "loading" }
  | { kind: "processing" }
  | { kind: "blocked"; detail: string | null }
  | { kind: "open" }
  | { kind: "completed" }
  | { kind: "error"; message: string }

export function EstimatePage() {
  const params = useParams()
  const id = Number(params.id)
  const location = useLocation()
  // Транзиентная справка по аномалиям: приходит только через navigate-state
  // при свежей загрузке; при прямом заходе по URL её нет (спека §5, этап 3).
  const notice = (location.state ?? {
    anomalies: [],
    outlineOverrides: 0,
  }) as NoticeState

  const [meta, setMeta] = useState<Meta>({ kind: "loading" })
  const [fileName, setFileName] = useState("")
  const [prog, setProg] = useState<Progress>({
    phase: "parsing", done: 0, total: 0, etaSeconds: null,
  })
  const [state, dispatch] = useReducer(reviewReducer, undefined, () =>
    initReview("", [])
  )

  const load = useCallback(async () => {
    setMeta({ kind: "loading" })
    try {
      const detail = await getEstimate(id)
      setFileName(detail.fileName)
      if (detail.status === "blocked") {
        setMeta({ kind: "blocked", detail: detail.statusDetail })
        return
      }
      if (detail.status === "pending" || detail.status === "running") {
        setMeta({ kind: "processing" })
        const { fileName: fn, rows } = await pollEstimate(
          id,
          (status, done, total) => {
            setProg({
              phase: status === "running" ? "matching" : "parsing",
              done, total, etaSeconds: null,
            })
          }
        )
        dispatch({ type: "load", state: initReview(fn || detail.fileName, rows) })
        setMeta({ kind: "open" })
        return
      }
      dispatch({
        type: "load",
        state: initReview(detail.fileName, detail.rows),
      })
      setMeta(detail.completedAt !== null ? { kind: "completed" } : { kind: "open" })
    } catch (err) {
      console.error(err)
      setMeta({
        kind: "error",
        message: err instanceof Error ? err.message : "Не удалось открыть смету",
      })
    }
  }, [id])

  useEffect(() => {
    if (Number.isInteger(id)) void load()
  }, [id, load])

  function handleReview(
    rowNumber: number,
    action: ReviewActionKind,
    articleId?: number
  ) {
    void patchRowReview(id, rowNumber, action, articleId)
      .then((updated) => dispatch({ type: "syncRow", row: updated }))
      .catch((err: unknown) => {
        console.error(err)
        dispatch({ type: "reopen", row: rowNumber })
        toast.error(
          err instanceof Error ? err.message : "Не удалось сохранить решение"
        )
      })
  }

  async function handleExport() {
    try {
      const blob = await exportEstimate(id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${fileName.replace(/\.[^.]+$/, "")}_сопоставлено.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error(err)
      toast.error(err instanceof Error ? err.message : "Экспорт не удался")
    }
  }

  function toggleCompletion(completed: boolean) {
    setCompletion(id, completed)
      .then(({ completedAt }) =>
        setMeta(completedAt !== null ? { kind: "completed" } : { kind: "open" })
      )
      .catch((err: unknown) => {
        console.error(err)
        toast.error(
          err instanceof Error ? err.message : "Не удалось изменить статус сметы"
        )
      })
  }

  if (!Number.isInteger(id)) return <NotFound />
  if (meta.kind === "loading")
    return <p className="p-8 text-sm text-muted-foreground">Загрузка…</p>
  if (meta.kind === "processing")
    return <ProcessingScreen fileName={fileName} progress={prog} />
  if (meta.kind === "blocked" || meta.kind === "error")
    return (
      <div className="p-8">
        <Alert variant="destructive" role="alert">
          <AlertTitle>
            {meta.kind === "blocked" ? "Смета отклонена" : "Ошибка"}
          </AlertTitle>
          <AlertDescription>
            {meta.kind === "blocked" ? (meta.detail ?? "—") : meta.message}
          </AlertDescription>
        </Alert>
        <Link className="mt-4 inline-block text-sm underline" to="/estimates">
          ← Ко всем сметам
        </Link>
      </div>
    )
  if (meta.kind === "completed")
    return (
      <DoneScreen
        state={state}
        estimateId={id}
        onExport={() => void handleExport()}
        onResume={() => toggleCompletion(false)}
      />
    )
  return (
    <>
      <StructureNotice
        anomalies={notice.anomalies}
        outlineOverrides={notice.outlineOverrides}
      />
      <ReviewScreen
        state={state}
        dispatch={dispatch}
        onExport={() => void handleExport()}
        onComplete={() => toggleCompletion(true)}
        onReview={handleReview}
      />
    </>
  )
}

function NotFound() {
  return (
    <div className="p-8">
      <Alert variant="destructive" role="alert">
        <AlertTitle>Смета не найдена</AlertTitle>
      </Alert>
      <Link className="mt-4 inline-block text-sm underline" to="/estimates">
        ← Ко всем сметам
      </Link>
    </div>
  )
}
```

`App.tsx`: добавить `<Route path="/estimates/:id" element={<EstimatePage />} />`.

- [ ] **Step 3: ReviewScreen — шапка**

Заменить проп `onNewEstimate: () => void` на `onComplete: () => void`. В шапке ([ReviewScreen.tsx:147-156](frontend/src/pages/estimate/ReviewScreen.tsx#L147)):

```tsx
<div className="ml-auto flex items-center gap-2">
  <Button variant="ghost" size="sm" asChild>
    <Link to="/estimates">
      <ArrowLeft className="size-4" />
      Ко всем сметам
    </Link>
  </Button>
  <Button size="sm" variant="outline" onClick={onExport}>
    <Download className="size-4" />
    Выгрузить Excel
  </Button>
  {pending === 0 ? (
    <Button size="sm" onClick={onComplete}>
      <Check className="size-4" />
      Завершить
    </Button>
  ) : (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button size="sm">
          <Check className="size-4" />
          Завершить
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Остались нерешённые строки</AlertDialogTitle>
          <AlertDialogDescription>
            Осталось {pending} спорных строк без решения. Завершить проверку всё
            равно? Возобновить можно в любой момент.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Отмена</AlertDialogCancel>
          <AlertDialogAction onClick={onComplete}>
            Завершить всё равно
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )}
</div>
```

где `const pending = total - reviewed` (значения `reviewed`/`total` уже вычисляются в компоненте через `progress(state)`). Импорты: `Link` из `react-router-dom`, `ArrowLeft`, `Check` из `lucide-react`, AlertDialog-набор из `@/components/ui/alert-dialog`; иконку/импорт `Plus` убрать. Экспорт больше НЕ меняет фазу (это уже так — `onExport` теперь только скачивает).

- [ ] **Step 4: DoneScreen — возобновление**

Пропсы: `onNewEstimate: () => void` → убрать; добавить `onResume: () => void`. Вместо кнопки «＋ Загрузить следующую смету»:

```tsx
<div className="mt-4 flex flex-col items-center gap-2">
  <Button variant="outline" size="sm" onClick={onResume}>
    Возобновить проверку
  </Button>
  <Link to="/estimates" className="text-sm text-[var(--ds-accent-hover)]">
    ＋ Загрузить следующую смету
  </Link>
</div>
```

- [ ] **Step 5: Удалить кэш и мёртвый код**

- Удалить файлы: `src/pages/estimate/EstimateFlow.tsx`, `src/pages/estimate/EstimateFlow.test.tsx`, `src/lib/session.ts`, `src/lib/session.test.ts`.
- `grep -r "session\"" src/` и `grep -rn "loadReview\|saveReview\|clearReview\|loadEstimateId\|beforeunload" src/` — все оставшиеся упоминания убрать (AppShell уже почищен в Task 5).

- [ ] **Step 6: Обновить сломанные тесты и прогнать всё**

`ReviewScreen.test.tsx`: `onNewEstimate` → `onComplete`; рендер обернуть в `MemoryRouter` (в шапке появился `Link`). `DoneScreen.test.tsx`: `onNewEstimate` → `onResume`, обёртка `MemoryRouter`. `StartProcessing.test.tsx`: сценарии старта переехали в `EstimatesPage.test.tsx` — оставшееся про `ProcessingScreen` сохранить, про `EstimateFlow` удалить.

Run: `cd frontend; npx vitest run; npm run typecheck`
Expected: PASS, 0 ошибок.

- [ ] **Step 7: Ручная проверка потока**

Run: `just dev-back` и `just dev-front`; в браузере: загрузить смету → URL становится `/estimates/N`, идёт прогресс → ревью; решить строку, F5 — прогресс восстановился с сервера; «Завершить» → итоговый экран; F5 — снова итоговый; «Возобновить проверку» → ревью; прямая ссылка `/estimates/N` из другой вкладки — та же фаза; «назад» браузера работает.

- [ ] **Step 8: Commit**

```bash
git add -A frontend/src
git commit -m "feat(estimates): /estimates/:id — фаза из статуса сметы, Завершить/Возобновить, кэш ревью удалён"
```

---

### Task 8: Фронт — EstimateList: прогресс и «Показать ещё»

**Files:**
- Modify: `frontend/src/components/estimate/EstimateList.tsx`
- Test: `frontend/src/components/estimate/EstimateList.test.tsx` (обновить/дополнить)

**Interfaces:**
- Consumes: `listEstimates({limit, offset})` и поля `reviewedCount`/`totalReviewable`/`completedAt` (Task 4).
- Produces: колонка «Проверка»; кнопка «Показать ещё» при `items.length < total`.

- [ ] **Step 1: Падающие тесты**

```tsx
it("показывает прогресс ревью и бейдж завершённой", async () => {
  vi.mocked(listEstimates).mockResolvedValue({
    items: [
      { ...ITEM, id: 1, reviewedCount: 3, totalReviewable: 7, completedAt: null },
      { ...ITEM, id: 2, completedAt: "2026-07-02T12:00:00Z" },
    ],
    total: 2,
  })
  render(<EstimateList onOpen={vi.fn()} />, { wrapper: MemoryRouter })
  expect(await screen.findByText("3 из 7")).toBeInTheDocument()
  expect(screen.getByText("Завершена")).toBeInTheDocument()
})

it("«Показать ещё» дозагружает следующую страницу", async () => {
  vi.mocked(listEstimates)
    .mockResolvedValueOnce({ items: [{ ...ITEM, id: 1 }], total: 2 })
    .mockResolvedValueOnce({ items: [{ ...ITEM, id: 2 }], total: 2 })
  render(<EstimateList onOpen={vi.fn()} />, { wrapper: MemoryRouter })
  await userEvent.click(await screen.findByRole("button", { name: /Показать ещё/ }))
  expect(listEstimates).toHaveBeenLastCalledWith({ limit: 50, offset: 1 })
})
```

(`ITEM` — полный `EstimateListItem` со статусом `ready`; после дозагрузки в списке обе строки.)

Run: `cd frontend; npx vitest run src/components/estimate/EstimateList.test.tsx` — Expected: FAIL.

- [ ] **Step 2: Реализация**

В `EstimateList.tsx`:
- Состояние: `items: EstimateListItem[] | null`, `total: number` — загрузка `listEstimates({ limit: PAGE, offset })`, где `const PAGE = 50`; «Показать ещё» делает запрос с `offset: items.length` и конкатенирует (`setItems((prev) => [...(prev ?? []), ...r.items])`).
- Новая колонка `<TableHead>Проверка</TableHead>` после «Статус»; ячейка:

```tsx
<TableCell className="text-muted-foreground tabular-nums">
  {item.completedAt !== null ? (
    <Badge>Завершена</Badge>
  ) : item.totalReviewable > 0 ? (
    `${item.reviewedCount} из ${item.totalReviewable}`
  ) : (
    "—"
  )}
</TableCell>
```

- Кнопка под таблицей (shadcn `Button variant="outline"`), видима при `items.length < total`:

```tsx
{items.length < total && (
  <div className="pt-3">
    <Button variant="outline" size="sm" onClick={() => void loadMore()}>
      Показать ещё
    </Button>
  </div>
)}
```

- `triggerReload` (после удаления) сбрасывает на первую страницу.

- [ ] **Step 3: Зелёные тесты**

Run: `cd frontend; npx vitest run; npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src
git commit -m "feat(estimates): список — колонка прогресса ревью и постраничная дозагрузка"
```

---

### Task 9: Финализация — lint, полный прогон, devlog

**Files:**
- Create: `docs/devlog/2026-07-02-ux-stage1-router-lifecycle.md` (формат — по соседним файлам в `docs/devlog/`)
- Modify: `CLAUDE.md` (раздел «Фронтенд»)

- [ ] **Step 1: Полная верификация**

Run (из корня): `just lint; just test; cd frontend; npm run typecheck; npm run build`
Expected: всё зелёное, сборка успешна.

- [ ] **Step 2: Актуализировать CLAUDE.md**

В разделе «Фронтенд» абзац про моки потока смет устарел ещё до этого этапа — заменить на актуальное: поток смет ходит в реальный бэкенд; навигация — react-router (`/estimates`, `/estimates/:id`, `/articles`); фаза сметы выводится из `status`+`completed_at`; sessionStorage хранит только JWT (`ciw.auth.token`).

- [ ] **Step 3: Devlog**

Краткий отчёт: что сделано (ссылка на спеку §3), ломающие изменения API (`GET /estimates` → `{items,total}`; `PATCH /completion`), что удалено (session-кэш ревью, beforeunload, EstimateFlow). Отложенное — не сюда, а в `docs/TECH_DEBT.md` (если появилось).

- [ ] **Step 4: Commit**

```bash
git add docs CLAUDE.md
git commit -m "docs: devlog этапа 1 UX-роадмапа + актуализация CLAUDE.md по фронту"
```

---

## Самопроверка покрытия спеки (§3)

| Требование спеки | Задача |
|---|---|
| react-router, маршруты `/estimates`, `/estimates/:id`, `/articles`, логин-гейт поверх | 5, 6, 7 |
| Маппинг статус→экран, `completed_at` → итоговый экран, `blocked` | 7 |
| Табы → NavLink, «назад» работает, бренд кликабелен | 5 |
| Удаление sessionStorage-кэша ревью и `beforeunload` | 7 |
| «Проверено X из Y» в списке | 3, 8 |
| Поле `completed_at` + миграция | 1 |
| Эндпоинт завершения/возобновления, права владелец/админ | 2 |
| Пагинация списка + `reviewed/total` | 3, 8 |
| Справочник — без изменений | (нет задач — намеренно) |
| Кнопка «Завершить» с диалогом при нерешённых (§4.2c перенесено в этап 1 как минимальный носитель `completed_at`) | 7 |
| «Возобновить проверку» (§4.2d, минимальный носитель) | 7 |
