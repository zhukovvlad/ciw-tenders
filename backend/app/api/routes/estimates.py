"""Роут загрузки сметы и сопоставления строк со справочником."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_current_user, get_matching_service, get_parser
from app.api.schemas import MatchResultOut
from app.services.excel_parser import ExcelEstimateParser
from app.services.matching_service import MatchingService

router = APIRouter(
    prefix="/estimates", tags=["estimates"], dependencies=[Depends(get_current_user)]
)


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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    results = matching.match_rows(rows)
    return [MatchResultOut.from_entity(r) for r in results]
