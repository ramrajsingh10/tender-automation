from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException

from .. import schemas
from ..services.ingestion_client import IngestionClientError
from ..services.ingestion_manager import reset_rag_ingestion, start_ingestion_if_ready
from ..services.rag_client import RagClientError, get_rag_client
from ..services.storage import StorageServiceError, storage_service
from ..settings import storage_settings, upload_settings
from ..store import store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tenders", tags=["tenders"])


def _build_upload_limits() -> schemas.UploadLimits:
    return schemas.UploadLimits(
        max_file_size_bytes=upload_settings.max_file_size_bytes,
        allowed_mime_types=list(upload_settings.allowed_mime_types),
        max_files=upload_settings.max_files,
    )


@router.post("", response_model=schemas.CreateTenderResponse, status_code=201)
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
        rag_ingestion=session.rag_ingestion,
        rag_files=session.rag_files,
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
        rag_ingestion=session.rag_ingestion,
        rag_files=session.rag_files,
    )


@router.post("/{tender_id}/process", response_model=schemas.TenderStatusResponse)
def trigger_parsing(tender_id: UUID) -> schemas.TenderStatusResponse:
    try:
        session = store.get_session(tender_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not session.files:
        raise HTTPException(status_code=400, detail="No files uploaded for this tender.")

    if session.rag_ingestion.status != schemas.RagIngestionStatus.DONE:
        raise HTTPException(
            status_code=409,
            detail="RAG ingestion is not complete. Please wait for ingestion to finish before running the playbook.",
        )

    if not session.rag_files:
        raise HTTPException(
            status_code=409,
            detail="RAG ingestion completed without rag files. Retry ingestion before running the playbook.",
        )

    rag_file_ids = [rf.rag_file_name for rf in session.rag_files]

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
            rag_file_ids=rag_file_ids,
            forget_after_run=False,
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
        rag_ingestion=updated.rag_ingestion,
        rag_files=updated.rag_files,
    )


@router.get("/{tender_id}/ingestion")
def get_ingestion_status(tender_id: UUID) -> dict:
    try:
        session = store.get_session(tender_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "ragIngestion": session.rag_ingestion.model_dump(by_alias=True),
        "ragFiles": [rf.model_dump(by_alias=True) for rf in session.rag_files],
    }


@router.post("/{tender_id}/ingestion/retry")
def retry_ingestion(tender_id: UUID) -> dict:
    try:
        reset_rag_ingestion(tender_id)
        start_ingestion_if_ready(tender_id, force=True)
        session = store.get_session(tender_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IngestionClientError as exc:
        logger.exception("Retry ingestion failed for tender %s: %s", tender_id, exc)
        session = store.get_session(tender_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "ragIngestion": session.rag_ingestion.model_dump(by_alias=True),
        "ragFiles": [rf.model_dump(by_alias=True) for rf in session.rag_files],
    }


@router.delete("/{tender_id}/rag-files")
def delete_rag_files(tender_id: UUID) -> dict:
    try:
        session = store.get_session(tender_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    rag_file_ids = [rf.rag_file_name for rf in session.rag_files if rf.rag_file_name]
    if rag_file_ids:
        client = get_rag_client()
        try:
            client.delete_rag_files(rag_file_ids)
        except RagClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    reset_rag_ingestion(tender_id)
    session = store.get_session(tender_id)
    return {
        "ragIngestion": session.rag_ingestion.model_dump(by_alias=True),
        "ragFiles": [rf.model_dump(by_alias=True) for rf in session.rag_files],
    }


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



