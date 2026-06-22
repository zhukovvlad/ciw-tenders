"""Роут загрузки сметы и сопоставления строк со справочником."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import (
    get_current_user,
    get_estimate_service,
    get_matching_service,
    get_parser,
    get_settings,
)
from app.api.schemas import (
    EstimateDetailOut,
    EstimateSummaryOut,
    EstimateUploadResponse,
    MatchResultOut,
)
from app.core.config import Settings
from app.domain.entities import Role, User
from app.domain.errors import StorageError
from app.services.estimate_service import EstimateService
from app.services.excel_parser import ExcelEstimateParser
from app.services.matching_service import MatchingService

router = APIRouter(
    prefix="/estimates", tags=["estimates"], dependencies=[Depends(get_current_user)]
)

_XLSX_SIGNATURE = b"PK\x03\x04"


@router.post("/match", response_model=list[MatchResultOut])
async def match_estimate(
    file: UploadFile = File(...),
    parser: ExcelEstimateParser = Depends(get_parser),
    matching: MatchingService = Depends(get_matching_service),
) -> list[MatchResultOut]:
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ожидается файл Excel (.xlsx/.xls)",
        )

    content = await file.read()
    try:
        rows = parser.parse(content)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    results = matching.match_rows(rows)
    return [MatchResultOut.from_entity(r) for r in results]


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
