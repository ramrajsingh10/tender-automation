from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from cloudevents.http import from_http
from fastapi import FastAPI, HTTPException, Request, status
from google.auth import exceptions as auth_exceptions
from google.cloud import firestore, storage
from google.cloud.firestore import Client as FirestoreClient
from google.cloud.storage import Client as StorageClient
from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    project_id: str = os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT", "")
    parsed_bucket: str = os.getenv("PARSED_TENDER_BUCKET", "parsedtenderdata")
    raw_bucket: str = os.getenv("RAW_TENDER_BUCKET", "rawtenderdata")
    ocr_jobs_collection: str = os.getenv("OCR_JOBS_COLLECTION", "ocrJobs")
    ocr_collection: str = os.getenv("OCR_COLLECTION", "ocrDocuments")
    tenders_collection: str = os.getenv("TENDERS_COLLECTION", "tenders")


settings = Settings()
_storage_client: StorageClient | None = None
_firestore_client: FirestoreClient | None = None


class OCRProcessingError(RuntimeError):
    """Raised when OCR output is missing or corrupt."""


def get_storage_client() -> StorageClient:
    global _storage_client
    if _storage_client is not None:
        return _storage_client
    try:
        _storage_client = storage.Client(project=settings.project_id or None)
    except auth_exceptions.DefaultCredentialsError as exc:
        raise RuntimeError(
            "Google Cloud Storage credentials not configured. Set GOOGLE_APPLICATION_CREDENTIALS "
            "or point to the storage emulator via STORAGE_EMULATOR_HOST."
        ) from exc
    return _storage_client


def get_firestore_client() -> FirestoreClient:
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client
    try:
        _firestore_client = firestore.Client(project=settings.project_id or None)
    except auth_exceptions.DefaultCredentialsError as exc:
        raise RuntimeError(
            "Firestore credentials not configured. Set GOOGLE_APPLICATION_CREDENTIALS or "
            "FIRESTORE_EMULATOR_HOST before using the ingest API."
        ) from exc
    return _firestore_client


class PipelineNormalizeRequest(BaseModel):
    tenderId: str
    ingestJobId: str | None = None

    class Config:
        populate_by_name = True
        extra = "ignore"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Tender Ingest API",
        description="Receives Document AI finalize events and launches the pipeline.",
        version="0.1.0",
    )

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/eventarc/document-finalized", status_code=status.HTTP_202_ACCEPTED)
    async def handle_eventarc(request: Request) -> dict[str, Any]:
        body = await request.body()
        try:
            event = from_http(dict(request.headers), body)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to parse CloudEvent.")
            raise HTTPException(status_code=400, detail=f"Invalid CloudEvent: {exc}") from exc

        data = event.data or {}
        bucket = data.get("bucket")
        object_name = data.get("name")
        event_id = event.get("id")

        if bucket != settings.parsed_bucket:
            logger.info(
                "Ignoring finalize event for bucket %s (expected %s).",
                bucket,
                settings.parsed_bucket,
            )
            return {"status": "ignored"}

        if not object_name or not object_name.endswith(".json"):
            logger.info("Ignoring object %s (not a JSON Document AI output).", object_name)
            return {"status": "ignored"}

        tender_id = _extract_tender_id(object_name)
        if not tender_id:
            logger.warning("Unable to determine tenderId from object %s.", object_name)
            return {"status": "ignored"}

        logger.info("Processing DocAI finalize event for tender %s (%s).", tender_id, object_name)

        output_uris = _list_output_objects(tender_id)
        raw_uris = _list_raw_objects(tender_id)

        try:
            documents = _load_docai_documents(output_uris)
            ocr_document = build_ocr_document(
                documents,
                tender_id=tender_id,
                raw_uris=raw_uris,
                docai_output_uris=output_uris,
            )
        except OCRProcessingError as exc:
            logger.exception("Failed to build OCR document for tender %s.", tender_id)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        now = datetime.now(timezone.utc)
        firestore_client = get_firestore_client()
        job_ref = firestore_client.collection(settings.ocr_jobs_collection).document()
        job_payload = {
            "tenderId": tender_id,
            "eventId": event_id,
            "docAiOutputUris": output_uris,
            "rawObjectUris": raw_uris,
            "startedAt": now.isoformat(),
            "status": "stored",
        }
        job_ref.set(job_payload)

        firestore_client.collection(settings.ocr_collection).document(tender_id).set(
            ocr_document, merge=True
        )

        _ensure_tender_stub(tender_id, now)

        firestore_client.collection(settings.ocr_jobs_collection).document(job_ref.id).update(
            {"status": "stored", "storedAt": datetime.now(timezone.utc).isoformat()}
        )

        logger.info("Stored OCR payload for tender %s (job %s).", tender_id, job_ref.id)
        return {"status": "stored", "tenderId": tender_id, "ocrJobId": job_ref.id}

    @app.post("/pipeline/normalize", status_code=status.HTTP_200_OK)
    async def acknowledge_normalization(payload: PipelineNormalizeRequest) -> dict[str, str]:
        tender_id = payload.tenderId
        if not tender_id:
            raise HTTPException(status_code=400, detail="tenderId is required.")

        now = datetime.now(timezone.utc).isoformat()
        firestore_client = get_firestore_client()
        logger.info(
            "Received pipeline normalization acknowledgement for tender %s (ingestJobId=%s).",
            tender_id,
            payload.ingestJobId,
        )

        firestore_client.collection(settings.tenders_collection).document(tender_id).set(
            {
                "tenderId": tender_id,
                "lastUpdated": now,
                "pipeline": {"normalizedAt": now},
            },
            merge=True,
        )

        if payload.ingestJobId:
            firestore_client.collection(settings.ocr_jobs_collection).document(payload.ingestJobId).set(
                {"tenderId": tender_id, "status": "normalized", "normalizedAt": now},
                merge=True,
            )

        return {"status": "ack", "tenderId": tender_id}

    return app


def _extract_tender_id(object_name: str) -> str | None:
    """Extract tenderId from parsed output path `tenderId/docai/output/file.json`."""
    parts = object_name.split("/")
    if len(parts) < 3:
        return None
    tender_id, docai_dir, output_dir = parts[:3]
    if docai_dir != "docai" or output_dir != "output":
        return None
    return tender_id


def _list_output_objects(tender_id: str) -> list[str]:
    prefix = f"{tender_id}/docai/output/"
    bucket = get_storage_client().bucket(settings.parsed_bucket)
    return [
        f"gs://{settings.parsed_bucket}/{blob.name}"
        for blob in bucket.list_blobs(prefix=prefix)
        if blob.name.endswith(".json")
    ]


def _list_raw_objects(tender_id: str) -> list[str]:
    prefix = f"{tender_id}/"
    bucket = get_storage_client().bucket(settings.raw_bucket)
    return [
        f"gs://{settings.raw_bucket}/{blob.name}"
        for blob in bucket.list_blobs(prefix=prefix)
    ]


def _load_docai_documents(output_uris: list[str]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for uri in output_uris:
        bucket_name, blob_name = _parse_gcs_uri(uri)
        bucket = get_storage_client().bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            raise OCRProcessingError(f"Document AI output {uri} not found.")
        payload = json.loads(blob.download_as_bytes())
        document = payload.get("document") if isinstance(payload, dict) else None
        if not document:
            raise OCRProcessingError(f"Document AI file {uri} missing 'document' field.")
        documents.append(document)
    return documents


def _parse_gcs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise OCRProcessingError(f"Unsupported GCS URI: {uri}")
    _, remainder = uri.split("gs://", 1)
    bucket, _, object_name = remainder.partition("/")
    if not bucket or not object_name:
        raise OCRProcessingError(f"Invalid GCS URI: {uri}")
    return bucket, object_name


def _ensure_tender_stub(tender_id: str, timestamp: datetime) -> None:
    firestore_client = get_firestore_client()
    tender_ref = firestore_client.collection(settings.tenders_collection).document(tender_id)
    tender_ref.set(
        {
            "tenderId": tender_id,
            "status": "ingest-received",
            "lastUpdated": timestamp.isoformat(),
        },
        merge=True,
    )


app = create_app()


def build_ocr_document(
    documents: list[dict[str, Any]],
    *,
    tender_id: str,
    raw_uris: list[str],
    docai_output_uris: list[str],
) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    pages: list[dict[str, Any]] = []
    fallback_page_number = 0

    for document in documents:
        full_text = document.get("text", "")
        for page in document.get("pages", []):
            fallback_page_number += 1
            page_number = page.get("pageNumber") or fallback_page_number
            page_text = _extract_text_from_layout(page.get("layout", {}), full_text)
            if not page_text.strip():
                # Fallback to concatenating paragraph text if page layout is missing.
                paragraph_text = [
                    _extract_text_from_layout(paragraph.get("layout", {}), full_text)
                    for paragraph in page.get("paragraphs", [])
                ]
                page_text = "\n".join(segment for segment in paragraph_text if segment).strip()

            pages.append(
                {
                    "pageNumber": page_number,
                    "text": page_text,
                    "detectedLanguages": page.get("detectedLanguages", []),
                    "dimension": page.get("dimension", {}),
                }
            )

    if not pages:
        raise OCRProcessingError("OCR output did not contain any pages.")

    return {
        "tenderId": tender_id,
        "source": {
            "docAiOutput": docai_output_uris,
            "rawBundle": raw_uris,
        },
        "pages": pages,
        "createdAt": timestamp,
        "schemaVersion": 1,
    }


def _extract_text_from_layout(layout: dict[str, Any], full_text: str) -> str:
    text_anchor = (layout or {}).get("textAnchor", {})
    segments = text_anchor.get("textSegments", [])
    if not segments:
        return ""
    fragments: list[str] = []
    for segment in segments:
        start = int(segment.get("startIndex", 0))
        end = int(segment.get("endIndex", 0))
        fragments.append(full_text[start:end])
    return "".join(fragments)
