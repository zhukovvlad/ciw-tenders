"""Роуты управления эталонным справочником статей СМР."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import get_article_service, get_current_user, require_admin
from app.api.schemas import ArticleCreate, ArticleOut
from app.services.article_service import ArticleService

router = APIRouter(prefix="/articles", tags=["articles"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[ArticleOut])
def list_articles(
    limit: int = 100,
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
        section_name=payload.section_name,
    )
    return ArticleOut.from_entity(article)


@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_admin)])
def delete_article(
    article_id: int,
    service: ArticleService = Depends(get_article_service),
) -> None:
    service.delete(article_id)
