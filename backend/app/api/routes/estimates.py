"""Роут загрузки сметы и ре-триггера матчинга."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    get_article_service,
    get_current_user,
    get_decision_fund_service,
    get_estimate_export_service,
    get_estimate_repository,
    get_estimate_review_service,
    get_estimate_service,
    get_settings,
    get_stale_sweeper,
    get_task_queue,
    require_admin,
)
from app.api.schemas import (
    CompletionOut,
    CompletionToggleIn,
    EstimateDetailOut,
    EstimateListOut,
    EstimateRowOut,
    EstimateSummaryOut,
    EstimateUploadResponse,
    ReferenceToggleIn,
    ReviewDecisionIn,
    StructuralAnomalyOut,
)
from app.core.config import Settings
from app.domain.entities import Role, StoredEstimateRow, User
from app.domain.errors import (
    EstimateCompletedError,
    EstimateNotCompletableError,
    InvalidReviewActionError,
    RowNotMatchedError,
    RowNotReviewableError,
    StorageError,
)
from app.domain.ports import EstimateRepository, TaskQueue
from app.services.article_service import ArticleService
from app.services.decision_fund_service import DecisionFundService
from app.services.estimate_export_service import EstimateExportService
from app.services.estimate_review_service import EstimateReviewService
from app.services.estimate_service import EstimateService

router = APIRouter(
    prefix="/estimates", tags=["estimates"], dependencies=[Depends(get_current_user)]
)

_XLSX_SIGNATURE = b"PK\x03\x04"


def _collect_article_ids(rows: Iterable[StoredEstimateRow]) -> list[int]:
    """id статей, чьи крошки нужны payload'у: рекомендация + финал + кандидаты."""
    return sorted(
        {r.matched_article_id for r in rows if r.matched_article_id}
        | {r.final_article_id for r in rows if r.final_article_id}
        | {c.id for r in rows for c in r.candidates if c.id}
    )


@router.post("/{estimate_id}/match", status_code=status.HTTP_202_ACCEPTED)
def retrigger_match(
    estimate_id: int,
    user: User = Depends(get_current_user),
    repository: EstimateRepository = Depends(get_estimate_repository),
    task_queue: TaskQueue = Depends(get_task_queue),
    settings: Settings = Depends(get_settings),
    sweeper: Callable[[int, int], bool] = Depends(get_stale_sweeper),
) -> dict[str, str]:
    est = repository.get(estimate_id, user.id or 0, is_admin=user.role is Role.ADMIN)
    if est is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Смета не найдена")

    # Зависший running после жёсткого краша воркера: sweeper на выделенном коннекте берёт
    # advisory-лок как арбитр живости (занят → воркер жив → no-op) и сбрасывает running→pending.
    swept = est.status == "running" and sweeper(estimate_id, settings.task_time_limit_s)

    task_queue.enqueue_match(estimate_id)
    if swept:
        detail = "перезапущено после сбоя"
    elif est.status == "running":
        detail = "уже выполняется"
    else:
        detail = "поставлено в очередь"
    return {"status": "accepted", "detail": detail}


@router.post("", response_model=EstimateUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_estimate(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
    settings: Settings = Depends(get_settings),
) -> EstimateUploadResponse:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Ожидается файл .xlsx")
    max_bytes = int(settings.estimate_max_upload_mb * 1024 * 1024)
    too_large = HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE,
        f"Файл больше {settings.estimate_max_upload_mb} МБ",
    )
    if file.size is not None and file.size > max_bytes:  # быстрый путь, если size заполнен
        raise too_large
    content = await file.read()
    if len(content) > max_bytes:  # авторитетный бэкстоп — не зависит от версии Starlette
        raise too_large
    if not content.startswith(_XLSX_SIGNATURE):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Файл не является .xlsx (ZIP)")

    try:
        result = service.ingest(content, file.filename, owner_id=user.id or 0)
    except ValueError as exc:  # нет обязательных колонок — до put в MinIO
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except StorageError as exc:  # ТОЛЬКО сбой MinIO → 503; прочее (БД и т.п.) → 500
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Хранилище недоступно") from exc

    return EstimateUploadResponse(
        id=result.estimate.id,
        status=result.estimate.status,
        nodes_count=len(result.estimate.rows),
        positions_count=result.positions_count,
        warnings=result.warnings,
        anomalies=[StructuralAnomalyOut(**asdict(a)) for a in result.anomalies],
        outline_overrides=result.outline_overrides,
    )


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


@router.get("/{estimate_id}", response_model=EstimateDetailOut)
def get_estimate(
    estimate_id: int,
    user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
    article_service: ArticleService = Depends(get_article_service),
) -> EstimateDetailOut:
    est = service.get(estimate_id, user.id or 0, is_admin=user.role is Role.ADMIN)
    if est is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Смета не найдена")
    ids = _collect_article_ids(est.rows)
    crumbs = article_service.ancestor_names_by_ids(ids) if ids else {}
    return EstimateDetailOut.from_entity(est, article_crumbs=crumbs)


@router.delete("/{estimate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_estimate(
    estimate_id: int,
    user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> None:
    if not service.delete(estimate_id, user.id or 0, is_admin=user.role is Role.ADMIN):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Смета не найдена")


@router.patch("/{estimate_id}/rows/{row_id}/review", response_model=EstimateRowOut)
def review_row(
    estimate_id: int,
    row_id: int,
    decision: ReviewDecisionIn,
    user: User = Depends(get_current_user),
    service: EstimateReviewService = Depends(get_estimate_review_service),
    article_service: ArticleService = Depends(get_article_service),
) -> EstimateRowOut:
    try:
        row = service.apply(
            estimate_id, row_id, decision.action, decision.article_id,
            user.id or 0, is_admin=user.role is Role.ADMIN,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except EstimateCompletedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except RowNotMatchedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except RowNotReviewableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except InvalidReviewActionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    # Крошка СТРОКИ не гидратируется здесь: её пересчёт требует всех строк сметы —
    # PATCH отдаёт крошки СТАТЕЙ (одной строки), breadcrumb остаётся [] (Task 6 мержит prev).
    ids = _collect_article_ids([row])
    crumbs = article_service.ancestor_names_by_ids(ids) if ids else {}
    return EstimateRowOut.from_entity(row, article_crumbs=crumbs)


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


@router.patch("/{estimate_id}/reference", status_code=status.HTTP_200_OK)
def toggle_reference(
    estimate_id: int,
    body: ReferenceToggleIn,
    user: User = Depends(get_current_user),
    fund_service: DecisionFundService = Depends(get_decision_fund_service),
    repository: EstimateRepository = Depends(get_estimate_repository),
) -> dict:
    # лёгкая проверка владения: get() тянул бы все строки с векторами ради 404
    if not repository.exists(estimate_id, user.id or 0, is_admin=user.role is Role.ADMIN):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Смета не найдена")
    if body.is_reference:
        promoted = fund_service.promote(estimate_id)  # 0 → is_reference не выставлен (см. Task 5)
        return {"is_reference": repository.is_reference(estimate_id), "promoted": promoted}
    fund_service.unreference(estimate_id)
    return {"is_reference": False, "promoted": 0}


@router.post("/fund/rebuild", status_code=status.HTTP_200_OK)
def rebuild_fund(
    user: User = Depends(require_admin),
    fund_service: DecisionFundService = Depends(get_decision_fund_service),
) -> dict:
    fund_service.rebuild()
    return {"status": "rebuilt"}


@router.get("/{estimate_id}/export")
def export_estimate(
    estimate_id: int,
    strict: bool = Query(False),
    user: User = Depends(get_current_user),
    service: EstimateExportService = Depends(get_estimate_export_service),
) -> StreamingResponse:
    try:
        data = service.export(
            estimate_id, user.id or 0, is_admin=user.role is Role.ADMIN, strict=strict
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except InvalidReviewActionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Хранилище недоступно") from exc
    filename = "estimate_matched.xlsx"
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
