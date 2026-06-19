"""Pydantic-схемы запросов/ответов API (DTO). Отделены от доменных сущностей."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.entities import MatchResult, TemplateArticle


class ArticleCreate(BaseModel):
    article_code: str = Field(..., examples=["СМР-01-001"])
    name: str = Field(..., examples=["Устройство монолитных бетонных фундаментов"])
    section_name: str = Field(..., examples=["Бетонные работы"])


class ArticleOut(BaseModel):
    id: int
    article_code: str
    name: str
    section_name: str

    @classmethod
    def from_entity(cls, entity: TemplateArticle) -> ArticleOut:
        return cls(
            id=entity.id or 0,
            article_code=entity.article_code,
            name=entity.name,
            section_name=entity.section_name,
        )


class CandidateOut(BaseModel):
    article_code: str
    name: str
    section_name: str
    score: float


class MatchResultOut(BaseModel):
    row_number: int
    source_name: str
    status: str
    score: float
    matched_code: str | None
    matched_name: str | None
    candidates: list[CandidateOut]

    @classmethod
    def from_entity(cls, result: MatchResult) -> MatchResultOut:
        return cls(
            row_number=result.source_row.row_number,
            source_name=result.source_row.name,
            status=result.status.value,
            score=round(result.score, 4),
            matched_code=result.matched_article.article_code if result.matched_article else None,
            matched_name=result.matched_article.name if result.matched_article else None,
            candidates=[
                CandidateOut(
                    article_code=c.article.article_code,
                    name=c.article.name,
                    section_name=c.article.section_name,
                    score=round(c.score, 4),
                )
                for c in result.candidates
            ],
        )
