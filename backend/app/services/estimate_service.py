"""Сценарии работы со сметами: ingest (парс → MinIO → БД) + list/get/delete."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.domain.entities import Estimate, EstimateSummary, NewEstimate
from app.domain.ports import EstimateRepository, ObjectStorage
from app.services.estimate_parser import EstimateParser

_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True, slots=True)
class IngestResult:
    estimate: Estimate
    positions_count: int
    warnings: list[str]


class EstimateService:
    def __init__(
        self,
        parser: EstimateParser,
        repository: EstimateRepository,
        storage: ObjectStorage,
    ) -> None:
        self._parser = parser
        self._repository = repository
        self._storage = storage

    def ingest(self, content: bytes, filename: str, owner_id: int) -> IngestResult:
        parsed = self._parser.parse(content)  # бросает ValueError (нет колонок) до put
        key = f"estimates/{uuid.uuid4().hex}/{filename}"
        self._storage.put(key, content, _XLSX_CONTENT_TYPE)  # падение → проброс, БД не тронута
        estimate = self._repository.create(
            NewEstimate(user_id=owner_id, filename=filename, original_object_key=key),
            parsed.nodes,
        )
        return IngestResult(
            estimate=estimate,
            positions_count=len(parsed.positions),
            warnings=parsed.warnings,
        )

    def list(self, owner_id: int, *, is_admin: bool) -> list[EstimateSummary]:
        return self._repository.list_for_owner(owner_id, is_admin=is_admin)

    def get(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> Estimate | None:
        return self._repository.get(estimate_id, requester_id, is_admin=is_admin)

    def delete(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> bool:
        key = self._repository.delete(estimate_id, requester_id, is_admin=is_admin)
        if key is None:
            return False
        try:
            self._storage.delete(key)  # best-effort: сирота подберёт реапер (тех-долг)
        except Exception:  # noqa: BLE001
            pass
        return True
