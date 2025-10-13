from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    textAnchors: list[dict[str, Any]] = Field(default_factory=list, alias="textAnchors")


class FactPayload(BaseModel):
    title: str | None = None
    dueAt: str | None = None
    amountText: str | None = None
    amountNumeric: float | None = None
    currency: str | None = None
    rawText: str | None = None
    sectionId: str | None = None
    pageRange: dict[str, int] | None = None
    rawUri: str | None = None


class FactResponse(BaseModel):
    id: str
    tenderId: UUID
    factType: str
    payload: FactPayload
    confidence: float | None = None
    status: str | None = None
    createdAt: str | None = None
    createdBy: str | None = None
    provenance: Provenance | None = None


class AnnexureResponse(BaseModel):
    id: str
    tenderId: UUID
    annexureType: str
    payload: FactPayload
    confidence: float | None = None
    status: str | None = None
    createdAt: str | None = None
    createdBy: str | None = None
    provenance: Provenance | None = None


class ListResponse(BaseModel):
    items: list[Any]


class ApprovalRequest(BaseModel):
    decision: str = Field(default="approved", pattern="^(approved|rejected)$")
    notes: str | None = None
