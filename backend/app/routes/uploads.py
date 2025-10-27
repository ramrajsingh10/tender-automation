from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException

from .. import schemas
from ..services.ingestion_client import IngestionClientError
from ..services.ingestion_manager import start_ingestion_if_ready
from ..services.storage import StorageServiceError, storage_service
from ..settings import storage_settings, upload_settings
from ..store import store

router = APIRouter(prefix="/api/tenders/{tender_id}/uploads", tags=["uploads"])

logger = logging.getLogger(__name__)
def _sanitize_filename(filename: str) -> str:
    """Return a filesystem-safe filename without path components."""
    basename = Path(filename).name
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
    sanitized = "".join(char if char in allowed else "_" for char in basename).strip("._")
    return sanitized or "file"


@router.post("/init", response_model=schemas.UploadInitResponse, status_code=201)
def init_upload(tender_id: UUID, request: schemas.UploadInitRequest) -> schemas.UploadInitResponse:
    try:
        session = store.get_session(tender_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if request.size_bytes > upload_settings.max_file_size_bytes:
        max_mb = upload_settings.max_file_size_bytes / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {max_mb:.2f} MB upload limit.",
        )

    if request.content_type not in upload_settings.allowed_mime_types:
        raise HTTPException(status_code=400, detail="File type is not permitted for upload.")

    if upload_settings.max_files is not None and len(session.files) >= upload_settings.max_files:
        raise HTTPException(
            status_code=409,
            detail=f"Maximum of {upload_settings.max_files} files reached for this tender.",
        )

    file_id = uuid4()
    sanitized_name = _sanitize_filename(request.filename)
    suffix = Path(sanitized_name).suffix.lower()
    stored_name = f"{file_id}{suffix}"
    object_name = f"{tender_id}/{stored_name}"
    storage_uri = f"gs://{storage_settings.raw_bucket}/{object_name}"

    try:
        signed_url = storage_service.generate_upload_signed_url(
            bucket_name=storage_settings.raw_bucket,
            object_name=object_name,
            content_type=request.content_type,
            expiration_seconds=storage_settings.signed_url_expiration_seconds,
        )
    except StorageServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    record = schemas.FileRecord(
        file_id=file_id,
        original_name=request.filename,
        stored_name=stored_name,
        content_type=request.content_type,
        size_bytes=request.size_bytes,
        storage_uri=storage_uri,
        status="uploading",
    )
    try:
        store.add_or_update_file(tender_id, record)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return schemas.UploadInitResponse(
        file_id=file_id,
        upload_url=signed_url,
        required_headers={"Content-Type": request.content_type},
        storage_path=object_name,
        storage_uri=storage_uri,
    )


@router.post("/{file_id}/complete", response_model=schemas.FileRecord)
def complete_upload(
    tender_id: UUID,
    file_id: UUID,
    request: schemas.UploadCompletionRequest,
) -> schemas.FileRecord:
    try:
        session = store.get_session(tender_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        existing = next(file for file in session.files if file.file_id == file_id)
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found for tender {tender_id}") from exc

    now = datetime.now(timezone.utc)
    if request.status == "uploaded":
        updated = existing.copy(
            update={"status": "uploaded", "uploaded_at": now, "error": None},
        )
    else:
        updated = existing.copy(
            update={
                "status": "failed",
                "uploaded_at": None,
                "error": request.error or "Upload failed.",
            }
        )

    store.add_or_update_file(tender_id, updated)
    try:
        start_ingestion_if_ready(tender_id)
    except IngestionClientError as exc:
        logger.debug("RAG ingestion trigger failed for tender %s: %s", tender_id, exc)
    return updated


