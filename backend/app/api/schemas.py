"""Pydantic-схемы запросов/ответов API (DTO). Отделены от доменных сущностей."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.domain.entities import (
    Estimate,
    EstimateSummary,
    ImportReport,
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


class MatchCandidateOut(BaseModel):
    id: int | None
    code: str
    name: str
    score: float


class EstimateRowOut(BaseModel):
    id: int
    code: str
    name: str
    parent_code: str | None
    section_type: str | None
    depth: int
    status: str
    matched_article_id: int | None = None
    matched_code: str | None = None
    matched_name: str | None = None
    score: float | None = None
    candidates: list[MatchCandidateOut] = []
    review_status: str = "unreviewed"
    final_article_id: int | None = None
    final_code: str | None = None
    final_name: str | None = None
    reviewed_at: datetime | None = None

    @classmethod
    def from_entity(cls, r: StoredEstimateRow) -> EstimateRowOut:
        return cls(
            id=r.id, code=r.code, name=r.name, parent_code=r.parent_code,
            section_type=r.section_type, depth=r.depth, status=r.status,
            matched_article_id=r.matched_article_id, matched_code=r.matched_code,
            matched_name=r.matched_name, score=r.score,
            candidates=[
                MatchCandidateOut(id=c.id, code=c.code, name=c.name, score=c.score)
                for c in r.candidates
            ],
            review_status=r.review_status, final_article_id=r.final_article_id,
            final_code=r.final_code, final_name=r.final_name, reviewed_at=r.reviewed_at,
        )


class EstimateDetailOut(BaseModel):
    id: int
    filename: str
    status: str
    status_detail: str | None = None
    created_at: datetime
    rows: list[EstimateRowOut]

    @classmethod
    def from_entity(cls, e: Estimate) -> EstimateDetailOut:
        return cls(
            id=e.id, filename=e.filename, status=e.status, status_detail=e.status_detail,
            created_at=e.created_at, rows=[EstimateRowOut.from_entity(r) for r in e.rows],
        )


