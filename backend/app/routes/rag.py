from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.rag_client import RagClientError, get_rag_client

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
    client = get_rag_client()
    try:
        return client.query(
            tender_id=request.tenderId,
            question=request.question,
            top_k=request.topK,
            conversation_id=request.conversationId,
        )
    except RagClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
