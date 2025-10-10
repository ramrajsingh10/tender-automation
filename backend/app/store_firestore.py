from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from google.cloud import firestore

from . import schemas
from .settings import upload_settings


class FirestoreTenderStore:
    """Firestore-backed tender session store for Cloud Run deployments."""

    def __init__(self, collection_name: str) -> None:
        self._client = firestore.Client()
        self._collection = self._client.collection(collection_name)

    @staticmethod
    def _serialize(session: schemas.TenderSession) -> dict:
        return session.model_dump(by_alias=True, mode="python")

    @staticmethod
    def _deserialize(data: dict | None) -> schemas.TenderSession:
        if not data:
            raise KeyError("Tender session not found")
        return schemas.TenderSession.model_validate(data)

    def _get_session(self, tender_id: UUID) -> schemas.TenderSession:
        snapshot = self._collection.document(str(tender_id)).get()
        if not snapshot.exists:
            raise KeyError(f"Tender session {tender_id} not found")
        return self._deserialize(snapshot.to_dict())

    def _write_session(self, session: schemas.TenderSession) -> None:
        self._collection.document(str(session.tender_id)).set(self._serialize(session))

    def create_session(self, created_by: Optional[str] = None) -> schemas.TenderSession:
        session = schemas.TenderSession(
            tender_id=uuid4(),
            status=schemas.TenderStatus.UPLOADING,
            created_at=datetime.now(timezone.utc),
            created_by=created_by,
            files=[],
        )
        self._write_session(session)
        return session

    def get_session(self, tender_id: UUID) -> schemas.TenderSession:
        return self._get_session(tender_id)

    def list_sessions(self) -> list[schemas.TenderSession]:
        return [self._deserialize(doc.to_dict()) for doc in self._collection.stream()]

    def set_status(self, tender_id: UUID, status: schemas.TenderStatus) -> schemas.TenderSession:
        session = self._get_session(tender_id)
        session.status = status
        self._write_session(session)
        return session

    def add_or_update_file(self, tender_id: UUID, record: schemas.FileRecord) -> schemas.TenderSession:
        session = self._get_session(tender_id)

        for idx, existing in enumerate(session.files):
            if existing.file_id == record.file_id:
                session.files[idx] = record
                break
        else:
            if upload_settings.max_files is not None and len(session.files) >= upload_settings.max_files:
                raise ValueError("Maximum number of files reached for this tender session.")
            session.files.append(record)

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

        self._write_session(session)
        return session

    def mark_parsing_started(
        self,
        tender_id: UUID,
        *,
        operation_name: str,
        input_prefix: str,
        output_prefix: str,
    ) -> schemas.TenderSession:
        session = self._get_session(tender_id)
        now = datetime.now(timezone.utc)
        session.status = schemas.TenderStatus.PARSING
        session.parse.operation_name = operation_name
        session.parse.input_prefix = input_prefix
        session.parse.output_prefix = output_prefix
        session.parse.started_at = now
        session.parse.completed_at = None
        session.parse.last_checked_at = now
        session.parse.error = None
        self._write_session(session)
        return session

    def mark_parsing_checked(self, tender_id: UUID) -> None:
        session = self._get_session(tender_id)
        session.parse.last_checked_at = datetime.now(timezone.utc)
        self._write_session(session)

    def mark_parsing_succeeded(self, tender_id: UUID, output_uri: str | None = None) -> schemas.TenderSession:
        session = self._get_session(tender_id)
        now = datetime.now(timezone.utc)
        session.status = schemas.TenderStatus.PARSED
        session.parse.completed_at = now
        session.parse.last_checked_at = now
        if output_uri:
            session.parse.output_uri = output_uri
        session.parse.error = None
        self._write_session(session)
        return session

    def mark_parsing_failed(self, tender_id: UUID, error_message: str) -> schemas.TenderSession:
        session = self._get_session(tender_id)
        now = datetime.now(timezone.utc)
        session.status = schemas.TenderStatus.FAILED
        session.parse.completed_at = now
        session.parse.last_checked_at = now
        session.parse.error = error_message
        self._write_session(session)
        return session
