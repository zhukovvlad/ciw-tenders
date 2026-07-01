"""Роут загрузки сметы и ре-триггера матчинга."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
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
    EstimateDetailOut,
    EstimateRowOut,
    EstimateSummaryOut,
    EstimateUploadResponse,
    ReferenceToggleIn,
    ReviewDecisionIn,
    StructuralAnomalyOut,
)
from app.core.config import Settings
from app.domain.entities import Role, User
from app.domain.errors import InvalidReviewActionError, RowNotMatchedError, StorageError
from app.domain.ports import EstimateRepository, TaskQueue
from app.services.decision_fund_service import DecisionFundService
from app.services.estimate_export_service import EstimateExportService
from app.services.estimate_review_service import EstimateReviewService
from app.services.estimate_service import EstimateService

router = APIRouter(
    prefix="/estimates", tags=["estimates"], dependencies=[Depends(get_current_user)]
)

_XLSX_SIGNATURE = b"PK\x03\x04"


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


@router.get("", response_model=list[EstimateSummaryOut])
def list_estimates(
    user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> list[EstimateSummaryOut]:
    is_admin = user.role is Role.ADMIN
    items = service.list(user.id or 0, is_admin=is_admin)
    return [EstimateSummaryOut.from_entity(s) for s in items]


@router.get("/{estimate_id}", response_model=EstimateDetailOut)
def get_estimate(
    estimate_id: int,
    user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> EstimateDetailOut:
    est = service.get(estimate_id, user.id or 0, is_admin=user.role is Role.ADMIN)
    if est is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Смета не найдена")
    return EstimateDetailOut.from_entity(est)


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
) -> EstimateRowOut:
    try:
        row = service.apply(
            estimate_id, row_id, decision.action, decision.article_id,
            user.id or 0, is_admin=user.role is Role.ADMIN,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except RowNotMatchedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except InvalidReviewActionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return EstimateRowOut.from_entity(row)


@router.patch("/{estimate_id}/reference", status_code=status.HTTP_200_OK)
def toggle_reference(
    estimate_id: int,
    body: ReferenceToggleIn,
    user: User = Depends(get_current_user),
    fund_service: DecisionFundService = Depends(get_decision_fund_service),
    repository: EstimateRepository = Depends(get_estimate_repository),
) -> dict:
    est = repository.get(estimate_id, user.id or 0, is_admin=user.role == Role.ADMIN)
    if est is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Смета не найдена")
    if body.is_reference:
        promoted = fund_service.promote(estimate_id)  # 0 → is_reference не выставлен (см. Task 5)
        return {"is_reference": promoted > 0, "promoted": promoted}
    fund_service.unreference(estimate_id)
    return {"is_reference": False, "promoted": 0}


@router.post("/fund/rebuild", status_code=status.HTTP_202_ACCEPTED)
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
