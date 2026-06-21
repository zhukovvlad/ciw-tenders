"""Роуты управления эталонным справочником статей СМР."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import (
    get_article_service,
    get_current_user,
    get_template_ingest_service,
    require_admin,
)
from app.api.schemas import ArticleCreate, ArticleOut, ImportReportOut
from app.domain.errors import DeletionGuardError, TemplateValidationError
from app.services.article_service import ArticleService
from app.services.template_ingest_service import TemplateIngestService

router = APIRouter(prefix="/articles", tags=["articles"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[ArticleOut])
def list_articles(
    limit: int = 1000,
    offset: int = 0,
    service: ArticleService = Depends(get_article_service),
) -> list[ArticleOut]:
    return [ArticleOut.from_entity(a) for a in service.list(limit=limit, offset=offset)]


@router.post("", response_model=ArticleOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin)])
def create_article(
    payload: ArticleCreate,
    service: ArticleService = Depends(get_article_service),
) -> ArticleOut:
    article = service.create(
        article_code=payload.article_code,
        name=payload.name,
        parent_code=payload.parent_code,
    )
    return ArticleOut.from_entity(article)


@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_admin)])
def delete_article(
    article_id: int,
    service: ArticleService = Depends(get_article_service),
) -> None:
    service.delete(article_id)


@router.post("/import", response_model=ImportReportOut, dependencies=[Depends(require_admin)])
async def import_template(
    file: UploadFile = File(...),
    dry_run: bool = False,
    force: bool = False,
    service: TemplateIngestService = Depends(get_template_ingest_service),
) -> ImportReportOut:
    content = await file.read()
    try:
        report = service.import_template(content, dry_run=dry_run, force=force)
    except TemplateValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except DeletionGuardError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "force_required": True, "deleted": exc.deleted},
        ) from exc
    return ImportReportOut.from_entity(report)
