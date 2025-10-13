from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Iterable, List

from fastapi import FastAPI, HTTPException, status
from google.cloud import firestore
from pydantic import BaseModel, Field

from chunker import Chunk, chunk_document
from embedding import EmbeddingClient, VectorIndexClient


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IndexRequest(BaseModel):
    tenderId: str = Field(..., alias="tenderId")
    document: dict[str, Any]
    chunkSize: int | None = Field(default=None, alias="chunkSize")


class IndexResponse(BaseModel):
    tenderId: str
    chunksIndexed: int


def create_app() -> FastAPI:
    project = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("VERTEX_LOCATION", "us-central1")
    index_endpoint_id = os.environ.get("VERTEX_INDEX_ENDPOINT_ID")
    index_id = os.environ.get("VERTEX_INDEX_ID")

    if not project or not index_endpoint_id or not index_id:
        logger.warning("RAG indexer missing required environment variables; service may not function correctly.")

    chunk_size = int(os.environ.get("RAG_CHUNK_SIZE", "1200"))
    max_batch = int(os.environ.get("RAG_MAX_BATCH", "50"))

    firestore_client = firestore.Client(project=project)
    embed_client = EmbeddingClient(project=project, location=location)
    vector_client = VectorIndexClient(
        project=project,
        location=location,
        index_endpoint_id=index_endpoint_id,
        index_id=index_id,
    )

    app = FastAPI(
        title="RAG Indexer",
        description="Chunks tender documents and upserts embeddings to Vertex AI Vector Search.",
        version="0.1.0",
    )

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/index", response_model=IndexResponse, status_code=status.HTTP_202_ACCEPTED)
    def index(request: IndexRequest) -> IndexResponse:
        if not request.document:
            raise HTTPException(status_code=400, detail="Document payload is required")

        tender_id = request.tenderId
        try:
            chunks = chunk_document(
                tender_id,
                request.document.get("document", {}),
                max_chars=request.chunkSize or chunk_size,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to chunk document for tender %s", tender_id)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        if not chunks:
            logger.info("No chunks generated for tender %s", tender_id)
            return IndexResponse(tenderId=tender_id, chunksIndexed=0)

        _process_chunks(tender_id, chunks, embed_client, vector_client, firestore_client, max_batch)
        return IndexResponse(tenderId=tender_id, chunksIndexed=len(chunks))

    return app


def _process_chunks(
    tender_id: str,
    chunks: List[Chunk],
    embed_client: EmbeddingClient,
    vector_client: VectorIndexClient,
    firestore_client: firestore.Client,
    max_batch: int,
) -> None:
    texts = [chunk.text for chunk in chunks]
    embeddings = embed_client.embed(texts)
    if len(embeddings) != len(chunks):
        raise RuntimeError("Embedding count mismatch")

    datapoints = []
    for chunk, vector in zip(chunks, embeddings, strict=True):
        datapoints.append(
            {
                "datapoint_id": f"{tender_id}:{chunk.chunk_id}",
                "feature_vector": vector,
                "restricts": [
                    {"namespace": "tenderId", "allowList": [tender_id]},
                    {"namespace": "sectionId", "allowList": [str(chunk.metadata.get("sectionId", ""))]},
                ],
            }
        )

    _batched(vector_client.upsert, datapoints, max_batch)
    _persist_metadata(firestore_client, chunks)


def _batched(func, items: Iterable[Any], batch_size: int) -> None:
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= batch_size:
            func(batch)
            batch = []
    if batch:
        func(batch)


def _persist_metadata(firestore_client: firestore.Client, chunks: Iterable[Chunk]) -> None:
    batch = firestore_client.batch()
    collection = firestore_client.collection("ragChunks")
    for chunk in chunks:
        doc_ref = collection.document(f"{chunk.tender_id}_{chunk.chunk_id}")
        payload = {
            "tenderId": chunk.tender_id,
            "chunkId": chunk.chunk_id,
            "textHash": hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
            "metadata": chunk.metadata,
            "createdAt": firestore.SERVER_TIMESTAMP,
        }
        batch.set(doc_ref, payload)
    batch.commit()


app = create_app()
