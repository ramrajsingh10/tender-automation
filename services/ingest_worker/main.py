from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from google.api_core import exceptions as google_exceptions
from google.cloud import firestore
from google.cloud import pubsub_v1

try:
    from google.cloud import aiplatform_v1beta1  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("google-cloud-aiplatform must be installed for ingest worker") from exc

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@dataclass(frozen=True)
class Settings:
    project_id: str = os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT", "")
    rag_corpus_path: str = os.getenv("VERTEX_RAG_CORPUS_PATH", "")
    rag_branch: str = os.getenv("VERTEX_RAG_DEFAULT_BRANCH", "")
    firestore_collection: str = os.getenv("TENDERS_COLLECTION", "tenders")
    pubsub_topic: str = os.getenv("INGEST_TOPIC", "")
    rag_location: str = os.getenv("VERTEX_RAG_CORPUS_LOCATION", "")


settings = Settings()

firestore_client: firestore.Client | None = None
rag_client: aiplatform_v1beta1.VertexRagDataServiceClient | None = None
publisher_client: pubsub_v1.PublisherClient | None = None


def get_firestore_client() -> firestore.Client:
    global firestore_client
    if firestore_client is None:
        firestore_client = firestore.Client(project=settings.project_id or None)
    return firestore_client


def get_rag_client() -> aiplatform_v1beta1.VertexRagDataServiceClient:
    global rag_client
    if rag_client is None:
        client_options = None
        if settings.rag_location:
            client_options = {"api_endpoint": f"{settings.rag_location}-aiplatform.googleapis.com"}
        rag_client = aiplatform_v1beta1.VertexRagDataServiceClient(client_options=client_options)
    return rag_client


def get_publisher_client() -> pubsub_v1.PublisherClient:
    global publisher_client
    if publisher_client is None:
        publisher_client = pubsub_v1.PublisherClient()
    return publisher_client


async def await_operation(operation) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, operation.result)


def _rag_file_payload(name: str, source_uri: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    payload: Dict[str, Any] = {
        "ragFileName": name,
        "sourceUri": source_uri,
        "ragCorpusPath": settings.rag_corpus_path,
        "branch": settings.rag_branch,
        "createdAt": now,
    }
    return payload


def _publish_status(tender_id: str, status: str) -> None:
    if not settings.pubsub_topic:
        return
    topic = settings.pubsub_topic
    publisher = get_publisher_client()
    message = json.dumps({"tenderId": tender_id, "status": status}).encode("utf-8")
    publisher.publish(topic, data=message)


async def ingest_tender(tender_id: str, gcs_uris: List[str]) -> Dict[str, Any]:
    client = get_rag_client()
    firestore_db = get_firestore_client()
    doc_ref = firestore_db.collection(settings.firestore_collection).document(tender_id)

    doc_ref.set(
        {
            "ragIngestion": {
                "status": "running",
                "startedAt": datetime.now(timezone.utc).isoformat(),
                "completedAt": None,
                "lastError": None,
            }
        },
        merge=True,
    )
    _publish_status(tender_id, "running")

    request = aiplatform_v1beta1.ImportRagFilesRequest(
        parent=settings.rag_corpus_path,
        import_rag_files_config={"gcs_source": {"uris": gcs_uris}},
    )
    operation = client.import_rag_files(request=request)
    operation_name = getattr(getattr(operation, "operation", None), "name", None)

    try:
        await await_operation(operation)
    except google_exceptions.GoogleAPICallError as exc:
        error_message = str(exc)
        doc_ref.set(
            {
                "ragIngestion": {
                    "status": "failed",
                    "completedAt": datetime.now(timezone.utc).isoformat(),
                    "lastError": error_message,
                }
            },
            merge=True,
        )
        _publish_status(tender_id, "failed")
        raise

    rag_files: Dict[str, str] = {}
    for rag_file in client.list_rag_files(parent=settings.rag_corpus_path):
        gcs_source = getattr(rag_file, "gcs_source", None)
        if not gcs_source:
            continue
        uris = getattr(gcs_source, "uris", [])
        for uri in uris:
            if uri in gcs_uris:
                rag_files[uri] = rag_file.name

    rag_file_payloads = [_rag_file_payload(name, uri) for uri, name in rag_files.items()]

    doc_ref.set(
        {
            "ragIngestion": {
                "status": "done",
                "completedAt": datetime.now(timezone.utc).isoformat(),
                "operationName": operation_name,
                "lastError": None,
            },
            "ragFiles": rag_file_payloads,
        },
        merge=True,
    )
    _publish_status(tender_id, "done")
    return {"ragFiles": rag_file_payloads, "operationName": operation_name}


app = FastAPI(title="RAG Ingestion Worker", version="0.1.0")


@app.post("/ingest")
async def ingest(payload: Dict[str, Any]) -> Dict[str, Any]:
    tender_id = payload.get("tenderId")
    gcs_uris = payload.get("gcsUris", [])
    if not tender_id or not gcs_uris:
        raise HTTPException(status_code=400, detail="tenderId and gcsUris are required")
    try:
        return await ingest_tender(str(tender_id), list(gcs_uris))
    except google_exceptions.GoogleAPICallError as exc:
        raise HTTPException(status_code=502, detail=f"Ingestion failed: {exc}") from exc





