from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, HTTPException

from .. import schemas
from ..services.rag_client import RagClientError, get_rag_client
from ..services.storage import StorageServiceError, storage_service
from ..settings import storage_settings, upload_settings
from ..store import store

router = APIRouter(prefix="/api/tenders", tags=["tenders"])


def _build_upload_limits() -> schemas.UploadLimits:
    return schemas.UploadLimits(
        max_file_size_bytes=upload_settings.max_file_size_bytes,
        allowed_mime_types=list(upload_settings.allowed_mime_types),
        max_files=upload_settings.max_files,
    )


@router.post("/", response_model=schemas.CreateTenderResponse, status_code=201)
def create_tender_session(
    request: schemas.CreateTenderRequest | None = None,
) -> schemas.CreateTenderResponse:
    payload = request or schemas.CreateTenderRequest()
    session = store.create_session(created_by=payload.created_by)
    return schemas.CreateTenderResponse(
        tender_id=session.tender_id,
        status=session.status,
        upload_limits=_build_upload_limits(),
    )


@router.get("/{tender_id}", response_model=schemas.TenderStatusResponse)
def get_tender_session(tender_id: UUID) -> schemas.TenderStatusResponse:
    try:
        session = store.get_session(tender_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return schemas.TenderStatusResponse(
        tender_id=session.tender_id,
        status=session.status,
        files=session.files,
        created_at=session.created_at,
        parse=session.parse,
    )


@router.post("/{tender_id}/process", response_model=schemas.TenderStatusResponse)
def trigger_parsing(tender_id: UUID) -> schemas.TenderStatusResponse:
    try:
        session = store.get_session(tender_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not session.files:
        raise HTTPException(status_code=400, detail="No files uploaded for this tender.")

    raw_uris: list[str] = []
    for file in session.files:
        if file.status != "uploaded":
            raise HTTPException(
                status_code=409,
                detail="All files must be uploaded before processing can begin.",
            )
        if not file.storage_uri:
            raise HTTPException(
                status_code=500,
                detail="Uploaded file is missing its storage URI. Retry the upload before processing.",
            )
        raw_uris.append(file.storage_uri)

    input_prefix = f"gs://{storage_settings.raw_bucket}/{tender_id}/"
    output_prefix = f"gs://{storage_settings.parsed_bucket}/{tender_id}/rag/"

    store.mark_parsing_started(
        tender_id,
        operation_name="rag-playbook",
        input_prefix=input_prefix,
        output_prefix=output_prefix,
    )

    client = get_rag_client()
    try:
        playbook_response = client.run_playbook(
            tender_id=str(tender_id),
            gcs_uris=raw_uris,
            forget_after_run=True,
        )
    except RagClientError as exc:
        store.mark_parsing_failed(tender_id, str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    output_uri = playbook_response.get("outputUri")
    store.mark_parsing_succeeded(tender_id, output_uri=output_uri)

    updated = store.get_session(tender_id)
    return schemas.TenderStatusResponse(
        tender_id=updated.tender_id,
        status=updated.status,
        files=updated.files,
        created_at=updated.created_at,
        parse=updated.parse,
    )


@router.get("/{tender_id}/playbook")
def get_playbook_results(tender_id: UUID) -> dict:
    try:
        session = store.get_session(tender_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    output_uri = session.parse.output_uri
    if not output_uri:
        raise HTTPException(status_code=404, detail="Playbook results are not available yet.")

    if not output_uri.startswith("gs://"):
        raise HTTPException(status_code=500, detail="Stored playbook URI is invalid.")

    bucket, _, blob_name = output_uri[5:].partition("/")
    if not bucket or not blob_name:
        raise HTTPException(status_code=500, detail="Stored playbook URI is malformed.")

    try:
        raw = storage_service.download_text(bucket, blob_name)
    except StorageServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Stored playbook JSON is invalid: {exc}") from exc
