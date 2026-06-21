"""Сценарий импорта справочника: parse -> compute_plan -> (guard) -> apply_plan -> отчёт."""

from __future__ import annotations

from app.domain.entities import ImportPlan, ImportReport
from app.domain.errors import DeletionGuardError
from app.domain.ports import ArticleImportRepository
from app.services.import_planning import compute_plan, requires_force
from app.services.template_parser import ParseResult, TemplateParser


class TemplateIngestService:
    def __init__(self, parser: TemplateParser, repository: ArticleImportRepository) -> None:
        self._parser = parser
        self._repository = repository

    def import_template(
        self, content: bytes, *, dry_run: bool = False, force: bool = False
    ) -> ImportReport:
        parsed: ParseResult = self._parser.parse(content)  # бросает TemplateValidationError
        existing = self._repository.load_existing()
        plan = compute_plan(parsed.rows, existing)
        needs_force = requires_force(plan, existing_total=len(existing))

        # force_required считаем всегда — чтобы dry-run честно предупреждал о боевом 409.
        report = self._report(plan, parsed, dry_run=dry_run, force_required=needs_force)
        if dry_run:
            return report

        if needs_force and not force:
            roots = sum(1 for code in plan.delete_codes if "." not in code)
            raise DeletionGuardError(deleted=len(plan.delete_ids), roots_deleted=roots)

        self._repository.apply_plan(plan)
        return report

    @staticmethod
    def _report(
        plan: ImportPlan, parsed: ParseResult, *, dry_run: bool, force_required: bool
    ) -> ImportReport:
        pending = len(plan.inserts) + len(plan.updates)
        return ImportReport(
            created=len(plan.inserts),
            updated=len(plan.updates),
            deleted=len(plan.delete_ids),
            unchanged=plan.unchanged,
            skipped=list(parsed.skipped),
            pending_embeddings=pending,
            dry_run=dry_run,
            force_required=force_required,
        )
