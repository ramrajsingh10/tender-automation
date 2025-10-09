from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException

from .. import schemas
from ..services.storage import StorageServiceError, storage_service
from ..settings import storage_settings, upload_settings
from ..store import store

router = APIRouter(prefix="/api/tenders/{tender_id}/uploads", tags=["uploads"])

_INVALID_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_filename(filename: str) -> str:
    """Return a filesystem-safe filename without path components."""
    basename = Path(filename).name
    sanitized = _INVALID_FILENAME_CHARS.sub("_", basename).strip("._")
    return sanitized or "file"


@router.post("/init", response_model=schemas.UploadInitResponse, status_code=201)
def init_upload(tender_id: UUID, request: schemas.UploadInitRequest) -> schemas.UploadInitResponse:
    try:
        session = store.get_session(tender_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if request.size_bytes > upload_settings.max_file_size_bytes:
        raise HTTPException(status_code=400, detail="File exceeds the 5 MB upload limit.")

    if request.content_type not in upload_settings.allowed_mime_types:
        raise HTTPException(status_code=400, detail="File type is not permitted for upload.")

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
    store.add_or_update_file(tender_id, record)

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
    return updated
