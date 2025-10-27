from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from .. import schemas
from ..store import store
from .ingestion_client import IngestionClientError, get_ingestion_client

logger = logging.getLogger(__name__)


def _should_trigger_ingestion(session: schemas.TenderSession) -> bool:
    if not session.files:
        return False
    if any(file.storage_uri is None for file in session.files):
        return False
    if any(file.status != "uploaded" for file in session.files):
        return False
    if session.rag_ingestion.status in (
        schemas.RagIngestionStatus.RUNNING,
        schemas.RagIngestionStatus.DONE,
    ):
        return False
    return True


def _update_rag_metadata_from_response(tender_id: UUID, response: dict) -> None:
    rag_file_payloads = response.get("ragFiles", [])
    rag_files = [
        schemas.RagFile.model_validate(payload) for payload in rag_file_payloads
    ]
    store.set_rag_files(tender_id, rag_files)
    store.update_rag_ingestion(
        tender_id,
        status=schemas.RagIngestionStatus.DONE,
        completed_at=datetime.now(timezone.utc),
        operation_name=response.get("operationName"),
        last_error=None,
    )


def start_ingestion_if_ready(tender_id: UUID, *, force: bool = False) -> None:
    """Trigger ingestion if all uploads are complete."""
    session = store.get_session(tender_id)
    if not force and not _should_trigger_ingestion(session):
        return

    gcs_uris = [file.storage_uri for file in session.files if file.storage_uri]
    if not gcs_uris:
        logger.debug("No storage URIs available to ingest for tender %s.", tender_id)
        return

    now = datetime.now(timezone.utc)
    store.update_rag_ingestion(
        tender_id,
        status=schemas.RagIngestionStatus.RUNNING,
        started_at=now,
        completed_at=None,
        last_error=None,
    )

    ingestion_client = get_ingestion_client()
    try:
        response = ingestion_client.start_ingestion(
            tender_id=str(tender_id),
            gcs_uris=gcs_uris,  # type: ignore[arg-type]
        )
        _update_rag_metadata_from_response(tender_id, response)
    except IngestionClientError as exc:
        store.update_rag_ingestion(
            tender_id,
            status=schemas.RagIngestionStatus.FAILED,
            completed_at=datetime.now(timezone.utc),
            last_error=str(exc),
        )
        raise


def reset_rag_ingestion(tender_id: UUID) -> None:
    store.set_rag_files(tender_id, [])
    store.update_rag_ingestion(
        tender_id,
        status=schemas.RagIngestionStatus.PENDING,
        operation_name=None,
        started_at=None,
        completed_at=None,
        last_error=None,
    )

