from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.rag_client import RagClientError, get_rag_client
from ..store import store

router = APIRouter(prefix="/api/rag", tags=["rag"])


class RagQueryRequest(BaseModel):
    tenderId: str
    question: str
    conversationId: str | None = None
    topK: int | None = None

    class Config:
        populate_by_name = True


@router.post("/query")
def query_rag(request: RagQueryRequest) -> dict:
    try:
        tender_uuid = UUID(request.tenderId)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="tenderId must be a valid UUID.") from exc

    try:
        session = store.get_session(tender_uuid)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    rag_file_ids = [rf.rag_file_name for rf in session.rag_files if rf.rag_file_name]
    gcs_uris = [file.storage_uri for file in session.files if file.storage_uri]
    client = get_rag_client()
    try:
        return client.query(
            tender_id=request.tenderId,
            question=request.question,
            top_k=request.topK,
            conversation_id=request.conversationId,
            rag_file_ids=rag_file_ids or None,
            gcs_uris=gcs_uris or None,
        )
    except RagClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
