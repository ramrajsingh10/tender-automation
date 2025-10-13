from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException

from ..schemas_dashboard import AnnexureResponse, ApprovalRequest, FactResponse, ListResponse, Provenance
from ..services.firestore_client import get_firestore_client

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _build_fact(doc_snapshot: Any) -> FactResponse:
    payload = doc_snapshot.to_dict() or {}
    payload["id"] = doc_snapshot.id
    return FactResponse.model_validate(payload)


def _build_annexure(doc_snapshot: Any) -> AnnexureResponse:
    payload = doc_snapshot.to_dict() or {}
    payload["id"] = doc_snapshot.id
    return AnnexureResponse.model_validate(payload)


def _resolve_document_text(anchors: list[dict[str, Any]], tender_id: str) -> list[dict[str, Any]]:
    client = get_firestore_client()
    parsed_doc_ref = client.collection("parsedDocuments").document(tender_id)
    parsed_snapshot = parsed_doc_ref.get()
    if not parsed_snapshot.exists:
        return anchors

    parsed_doc = parsed_snapshot.to_dict() or {}
    text_index = parsed_doc.get("textIndex", {})
    documents = parsed_doc.get("document", {})
    text_lookup = text_index.get("anchors", {})
    page_map = {
        page.get("pageNumber"): page
        for page in (documents.get("pages") or [])
        if isinstance(page, dict)
    }

    resolved = []
    for anchor in anchors:
        details = dict(anchor)
        reference = text_lookup.get(anchor.get("anchorId"))
        if reference:
            page_number = reference.get("page")
            details["page"] = page_number
            page_data = page_map.get(page_number)
            page_text = None
            if page_data:
                for block in page_data.get("blocks", []):
                    if block.get("anchorId") == anchor.get("anchorId"):
                        page_text = block.get("text")
                        break
            details["snippet"] = page_text
            details["startIndex"] = reference.get("startIndex")
            details["endIndex"] = reference.get("endIndex")
        resolved.append(details)
    return resolved


def _resolve_provenance(entries: list[dict[str, Any]], tender_id: UUID) -> list[dict[str, Any]]:
    return _resolve_document_text(entries, str(tender_id))


@router.get("/tenders/{tender_id}/facts", response_model=ListResponse)
def list_facts(tender_id: UUID) -> ListResponse:
    client = get_firestore_client()
    facts_ref = client.collection("facts").where("tenderId", "==", str(tender_id))
    docs = facts_ref.stream()
    items = []
    for doc in docs:
        fact = _build_fact(doc)
        if fact.provenance and fact.provenance.textAnchors:
            resolved = _resolve_provenance(fact.provenance.textAnchors, tender_id)
            fact.provenance = Provenance(textAnchors=resolved)
        items.append(fact)
    return ListResponse(items=items)


@router.get("/tenders/{tender_id}/annexures", response_model=ListResponse)
def list_annexures(tender_id: UUID) -> ListResponse:
    client = get_firestore_client()
    annexures_ref = client.collection("annexures").where("tenderId", "==", str(tender_id))
    docs = annexures_ref.stream()
    items = []
    for doc in docs:
        annexure = _build_annexure(doc)
        if annexure.provenance and annexure.provenance.textAnchors:
            resolved = _resolve_provenance(annexure.provenance.textAnchors, tender_id)
            annexure.provenance = Provenance(textAnchors=resolved)
        items.append(annexure)
    return ListResponse(items=items)


@router.post("/facts/{fact_id}/decision")
def decide_fact(fact_id: str, request: ApprovalRequest) -> dict[str, str]:
    client = get_firestore_client()
    doc_ref = client.collection("facts").document(fact_id)
    snapshot = doc_ref.get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Fact not found")

    doc_ref.update(
        {
            "status": request.decision,
            "decisionAt": datetime.now(timezone.utc).isoformat(),
            "decisionNotes": request.notes,
        }
    )
    return {"status": request.decision}


@router.post("/annexures/{annexure_id}/decision")
def decide_annexure(annexure_id: str, request: ApprovalRequest) -> dict[str, str]:
    client = get_firestore_client()
    doc_ref = client.collection("annexures").document(annexure_id)
    snapshot = doc_ref.get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Annexure not found")

    doc_ref.update(
        {
            "status": request.decision,
            "decisionAt": datetime.now(timezone.utc).isoformat(),
            "decisionNotes": request.notes,
        }
    )
    return {"status": request.decision}
