from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException

from .. import schemas
from ..services.document_ai import DocumentAIServiceError, document_ai_service
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
def create_tender_session(request: schemas.CreateTenderRequest | None = None) -> schemas.CreateTenderResponse:
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
def trigger_parsing(tender_id: UUID, background_tasks: BackgroundTasks) -> schemas.TenderStatusResponse:
    try:
        session = store.get_session(tender_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not session.files:
        raise HTTPException(status_code=400, detail="No files uploaded for this tender.")
    if any(file.status != "uploaded" for file in session.files):
        raise HTTPException(status_code=409, detail="All files must be uploaded before parsing can begin.")
    if session.status == schemas.TenderStatus.PARSING:
        raise HTTPException(status_code=409, detail="Parsing is already in progress for this tender.")
    if not document_ai_service.is_configured:
        raise HTTPException(
            status_code=500,
            detail=(
                "Document AI processor is not configured. "
                "Set DOCUMENT_AI_LOCATION and DOCUMENT_AI_PROCESSOR_ID environment variables."
            ),
        )

    input_prefix = f"gs://{storage_settings.raw_bucket}/{tender_id}/"
    output_prefix = f"gs://{storage_settings.parsed_bucket}/{tender_id}/"

    try:
        operation_name = document_ai_service.start_batch_process(
            input_prefix=input_prefix,
            output_prefix=output_prefix,
        )
    except DocumentAIServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    store.mark_parsing_started(
        tender_id,
        operation_name=operation_name,
        input_prefix=input_prefix,
        output_prefix=output_prefix,
    )
    background_tasks.add_task(_monitor_operation, tender_id, operation_name, output_prefix)

    updated = store.get_session(tender_id)
    return schemas.TenderStatusResponse(
        tender_id=updated.tender_id,
        status=updated.status,
        files=updated.files,
        created_at=updated.created_at,
        parse=updated.parse,
    )


def _monitor_operation(tender_id: UUID, operation_name: str, output_prefix: str) -> None:
    try:
        result = document_ai_service.wait_for_operation(
            operation_name,
            interval_seconds=10,
            timeout_seconds=1800,
            progress_callback=lambda: store.mark_parsing_checked(tender_id),
        )
        output_uri = document_ai_service.extract_output_uri(result) or output_prefix
        store.mark_parsing_succeeded(tender_id, output_uri=output_uri)
    except DocumentAIServiceError as exc:
        store.mark_parsing_failed(tender_id, error_message=str(exc))
