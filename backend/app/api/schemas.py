"""Pydantic-схемы запросов/ответов API (DTO). Отделены от доменных сущностей."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.domain.entities import (
    Estimate,
    EstimateSummary,
    ImportReport,
    MatchResult,
    Role,
    StoredEstimateRow,
    TemplateArticle,
    User,
)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=1024)
    role: Role = Role.USER


class UserOut(BaseModel):
    id: int
    email: str
    role: Role
    is_active: bool
    created_at: datetime

    @classmethod
    def from_entity(cls, user: User) -> UserOut:
        return cls(
            id=user.id or 0,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,  # type: ignore[arg-type]
        )


class ArticleCreate(BaseModel):
    # код — только числовые сегменты через точку: list_all сортирует через cast в int[],
    # нечисловой код уронил бы GET /api/articles (см. Task 7).
    article_code: str = Field(..., pattern=r"^\d+(\.\d+)*$", examples=["1.4.1"])
    name: str = Field(..., min_length=1, examples=["Мокап фасада"])
    parent_code: str | None = Field(default=None, pattern=r"^\d+(\.\d+)*$", examples=["1.4"])


class ArticleOut(BaseModel):
    id: int
    article_code: str
    name: str
    parent_id: int | None

    @classmethod
    def from_entity(cls, entity: TemplateArticle) -> ArticleOut:
        return cls(
            id=entity.id or 0,
            article_code=entity.article_code,
            name=entity.name,
            parent_id=entity.parent_id,
        )


class DeleteAllResponse(BaseModel):
    deleted: int


class ImportReportOut(BaseModel):
    created: int
    updated: int
    deleted: int
    unchanged: int
    skipped: list[str]
    pending_embeddings: int
    dry_run: bool
    force_required: bool

    @classmethod
    def from_entity(cls, report: ImportReport) -> ImportReportOut:
        return cls(
            created=report.created,
            updated=report.updated,
            deleted=report.deleted,
            unchanged=report.unchanged,
            skipped=report.skipped,
            pending_embeddings=report.pending_embeddings,
            dry_run=report.dry_run,
            force_required=report.force_required,
        )


class EstimateUploadResponse(BaseModel):
    id: int
    status: str
    nodes_count: int
    positions_count: int
    warnings: list[str]


class EstimateSummaryOut(BaseModel):
    id: int
    filename: str
    status: str
    nodes_count: int
    created_at: datetime

    @classmethod
    def from_entity(cls, s: EstimateSummary) -> EstimateSummaryOut:
        return cls(
            id=s.id, filename=s.filename, status=s.status,
            nodes_count=s.nodes_count, created_at=s.created_at,
        )


class EstimateRowOut(BaseModel):
    code: str
    name: str
    parent_code: str | None
    section_type: str | None
    depth: int
    status: str

    @classmethod
    def from_entity(cls, r: StoredEstimateRow) -> EstimateRowOut:
        return cls(
            code=r.code, name=r.name, parent_code=r.parent_code,
            section_type=r.section_type, depth=r.depth, status=r.status,
        )


class EstimateDetailOut(BaseModel):
    id: int
    filename: str
    status: str
    created_at: datetime
    rows: list[EstimateRowOut]

    @classmethod
    def from_entity(cls, e: Estimate) -> EstimateDetailOut:
        return cls(
            id=e.id, filename=e.filename, status=e.status, created_at=e.created_at,
            rows=[EstimateRowOut.from_entity(r) for r in e.rows],
        )


class CandidateOut(BaseModel):
    article_code: str
    name: str
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
                    score=round(c.score, 4),
                )
                for c in result.candidates
            ],
        )
