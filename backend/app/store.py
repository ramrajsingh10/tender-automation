from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import UUID, uuid4

from . import schemas
from .settings import upload_settings


class TenderStore:
    """Thread-safe in-memory store for tender sessions.

    Intended for MVP/demo use. Replace with persistent storage (e.g. Firestore)
    when moving beyond Phase 1.
    """

    def __init__(self) -> None:
        self._sessions: Dict[UUID, schemas.TenderSession] = {}
        self._lock = threading.Lock()

    def create_session(self, created_by: Optional[str] = None) -> schemas.TenderSession:
        tender_id = uuid4()
        session = schemas.TenderSession(
            tender_id=tender_id,
            status=schemas.TenderStatus.UPLOADING,
            created_at=datetime.now(timezone.utc),
            created_by=created_by,
            files=[],
        )
        with self._lock:
            self._sessions[tender_id] = session
        return session

    def get_session(self, tender_id: UUID) -> schemas.TenderSession:
        try:
            return self._sessions[tender_id]
        except KeyError as exc:
            raise KeyError(f"Tender session {tender_id} not found") from exc

    def list_sessions(self) -> list[schemas.TenderSession]:
        with self._lock:
            return list(self._sessions.values())

    def set_status(self, tender_id: UUID, status: schemas.TenderStatus) -> schemas.TenderSession:
        with self._lock:
            session = self._sessions[tender_id]
            session.status = status
        return session

    def add_or_update_file(self, tender_id: UUID, record: schemas.FileRecord) -> schemas.TenderSession:
        with self._lock:
            session = self._sessions[tender_id]

            for idx, existing in enumerate(session.files):
                if existing.file_id == record.file_id:
                    session.files[idx] = record
                    break
            else:
                if upload_settings.max_files is not None and len(session.files) >= upload_settings.max_files:
                    raise ValueError("Maximum number of files reached for this tender session.")
                session.files.append(record)

            # if all files uploaded, update status
            if record.status == "failed":
                session.status = schemas.TenderStatus.FAILED
            elif session.files and all(f.status == "uploaded" for f in session.files):
                if session.status not in (schemas.TenderStatus.PARSING, schemas.TenderStatus.PARSED):
                    session.status = schemas.TenderStatus.UPLOADED
            elif session.status not in (
                schemas.TenderStatus.PARSING,
                schemas.TenderStatus.PARSED,
                schemas.TenderStatus.FAILED,
            ):
                session.status = schemas.TenderStatus.UPLOADING
        return session

    def mark_parsing_started(
        self,
        tender_id: UUID,
        *,
        operation_name: str,
        input_prefix: str,
        output_prefix: str,
    ) -> schemas.TenderSession:
        with self._lock:
            session = self._sessions[tender_id]
            now = datetime.now(timezone.utc)
            session.status = schemas.TenderStatus.PARSING
            session.parse.operation_name = operation_name
            session.parse.input_prefix = input_prefix
            session.parse.output_prefix = output_prefix
            session.parse.started_at = now
            session.parse.completed_at = None
            session.parse.last_checked_at = now
            session.parse.error = None
        return session

    def mark_parsing_checked(self, tender_id: UUID) -> None:
        with self._lock:
            session = self._sessions[tender_id]
            session.parse.last_checked_at = datetime.now(timezone.utc)

    def mark_parsing_succeeded(self, tender_id: UUID, output_uri: str | None = None) -> schemas.TenderSession:
        with self._lock:
            session = self._sessions[tender_id]
            now = datetime.now(timezone.utc)
            session.status = schemas.TenderStatus.PARSED
            session.parse.completed_at = now
            session.parse.last_checked_at = now
            if output_uri:
                session.parse.output_uri = output_uri
            session.parse.error = None
        return session

    def mark_parsing_failed(self, tender_id: UUID, error_message: str) -> schemas.TenderSession:
        with self._lock:
            session = self._sessions[tender_id]
            now = datetime.now(timezone.utc)
            session.status = schemas.TenderStatus.FAILED
            session.parse.completed_at = now
            session.parse.last_checked_at = now
            session.parse.error = error_message
        return session


store = TenderStore()
