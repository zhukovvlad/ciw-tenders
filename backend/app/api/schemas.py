"""Pydantic-схемы запросов/ответов API (DTO). Отделены от доменных сущностей."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.domain.classification import full_breadcrumbs
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


class ArticleSearchOut(BaseModel):
    id: int
    code: str
    name: str
    breadcrumb: list[str] = []


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


class StructuralAnomalyOut(BaseModel):
    """DTO построчной аномалии структуры (проброс из парсера в ответ загрузки)."""

    kind: str
    source_index: int
    code: str
    name: str
    detail: str


class EstimateUploadResponse(BaseModel):
    id: int
    status: str
    nodes_count: int
    positions_count: int
    warnings: list[str]
    anomalies: list[StructuralAnomalyOut] = []
    outline_overrides: int = 0


class EstimateSummaryOut(BaseModel):
    id: int
    filename: str
    status: str
    nodes_count: int
    created_at: datetime
    completed_at: datetime | None = None
    reviewed_count: int = 0
    total_reviewable: int = 0

    @classmethod
    def from_entity(cls, s: EstimateSummary) -> EstimateSummaryOut:
        return cls(
            id=s.id, filename=s.filename, status=s.status,
            nodes_count=s.nodes_count, created_at=s.created_at,
            completed_at=s.completed_at,
            reviewed_count=s.reviewed_count, total_reviewable=s.total_reviewable,
        )


class EstimateListOut(BaseModel):
    items: list[EstimateSummaryOut]
    total: int


class MatchCandidateOut(BaseModel):
    id: int | None
    code: str
    name: str
    score: float
    breadcrumb: list[str] = []


class EstimateRowOut(BaseModel):
    id: int
    code: str
    name: str
    parent_code: str | None
    section_type: str | None
    depth: int
    status: str
    source_index: int = 0
    matched_article_id: int | None = None
    matched_code: str | None = None
    matched_name: str | None = None
    score: float | None = None
    match_error: str | None = None
    candidates: list[MatchCandidateOut] = []
    review_status: str = "unreviewed"
    final_article_id: int | None = None
    final_code: str | None = None
    final_name: str | None = None
    reviewed_at: datetime | None = None
    breadcrumb: list[str] = []
    matched_breadcrumb: list[str] = []
    final_breadcrumb: list[str] = []

    @classmethod
    def from_entity(
        cls,
        r: StoredEstimateRow,
        *,
        breadcrumb: list[str] | None = None,
        article_crumbs: Mapping[int, list[str]] | None = None,
    ) -> EstimateRowOut:
        crumbs = article_crumbs or {}
        return cls(
            id=r.id, code=r.code, name=r.name, parent_code=r.parent_code,
            section_type=r.section_type, depth=r.depth, status=r.status,
            source_index=r.source_index, matched_article_id=r.matched_article_id,
            matched_code=r.matched_code, matched_name=r.matched_name, score=r.score,
            match_error=r.match_error,
            candidates=[
                MatchCandidateOut(
                    id=c.id, code=c.code, name=c.name, score=c.score,
                    breadcrumb=crumbs.get(c.id, []) if c.id else [],
                )
                for c in r.candidates
            ],
            review_status=r.review_status, final_article_id=r.final_article_id,
            final_code=r.final_code, final_name=r.final_name, reviewed_at=r.reviewed_at,
            breadcrumb=breadcrumb or [],
            matched_breadcrumb=(
                crumbs.get(r.matched_article_id, []) if r.matched_article_id else []
            ),
            final_breadcrumb=(
                crumbs.get(r.final_article_id, []) if r.final_article_id else []
            ),
        )


class ReviewDecisionIn(BaseModel):
    action: Literal["confirm", "pick", "reject"]
    article_id: int | None = None


class ReferenceToggleIn(BaseModel):
    is_reference: bool


class CompletionToggleIn(BaseModel):
    completed: bool


class CompletionOut(BaseModel):
    completed_at: datetime | None


class EstimateDetailOut(BaseModel):
    id: int
    filename: str
    status: str
    status_detail: str | None = None
    created_at: datetime
    is_reference: bool = False
    completed_at: datetime | None = None
    rows: list[EstimateRowOut]

    @classmethod
    def from_entity(
        cls, e: Estimate, *, article_crumbs: Mapping[int, list[str]] | None = None
    ) -> EstimateDetailOut:
        ordered = sorted(e.rows, key=lambda r: r.source_index)
        chains = full_breadcrumbs([(r.depth, r.name) for r in ordered])
        crumb_by_id = {r.id: c for r, c in zip(ordered, chains, strict=True)}
        rows = [
            EstimateRowOut.from_entity(
                r, breadcrumb=crumb_by_id[r.id], article_crumbs=article_crumbs
            )
            for r in e.rows
        ]
        return cls(
            id=e.id, filename=e.filename, status=e.status, status_detail=e.status_detail,
            created_at=e.created_at, is_reference=e.is_reference, completed_at=e.completed_at,
            rows=rows,
        )


