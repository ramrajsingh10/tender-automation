from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass
from typing import Iterable, Optional

import google.auth
from google.api_core.exceptions import GoogleAPIError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
from google.cloud import firestore, storage
import pikepdf


logger = logging.getLogger(__name__)


@dataclass
class AnnexureRecord:
    id: str
    tender_id: str
    name: str
    raw_uri: str
    page_range: Optional[dict]


class AnnexureArtifactGenerator:
    def __init__(self, *, parent_folder_id: str | None = None) -> None:
        self._firestore = firestore.Client()
        self._storage = storage.Client()
        self._drive_service = None
        self._parent_folder_id = parent_folder_id

    def generate(self, tender_id: str, annexure_ids: Optional[Iterable[str]] = None) -> list[dict]:
        records = self._fetch_annexures(tender_id, annexure_ids)
        if not records:
            logger.info("No annexures found for tender %s", tender_id)
            return []

        results: list[dict] = []
        for record in records:
            try:
                pdf_bytes = self._extract_pdf_bytes(record)
                upload = self._upload_to_drive(record, pdf_bytes)
                artifact = self._persist_artifact(record, upload)
                results.append(artifact)
            except HttpError as exc:
                logger.exception("Drive upload failed for annexure %s", record.id)
                raise RuntimeError(f"Failed to upload annexure {record.id} to Google Docs: {exc}") from exc
            except GoogleAPIError as exc:
                logger.exception("Google API error while processing annexure %s", record.id)
                raise RuntimeError(f"Google API error for annexure {record.id}: {exc}") from exc
        return results

    # ------------------------------------------------------------------
    # Firestore helpers
    # ------------------------------------------------------------------

    def _fetch_annexures(self, tender_id: str, annexure_ids: Optional[Iterable[str]]) -> list[AnnexureRecord]:
        query = self._firestore.collection("annexures").where("tenderId", "==", tender_id)
        if annexure_ids:
            query = query.where("__name__", "in", list(annexure_ids))

        records: list[AnnexureRecord] = []
        for snapshot in query.stream():
            payload = snapshot.to_dict() or {}
            status = (payload.get("status") or "").lower()
            if status and status != "approved":
                logger.info("Skipping annexure %s with status %s", snapshot.id, status)
                continue
            annexure_payload = payload.get("payload") or {}
            raw_uri = annexure_payload.get("rawUri")
            if not raw_uri:
                logger.warning("Annexure %s missing rawUri; skipping", snapshot.id)
                continue
            name = annexure_payload.get("name") or payload.get("annexureType") or snapshot.id
            records.append(
                AnnexureRecord(
                    id=snapshot.id,
                    tender_id=tender_id,
                    name=name,
                    raw_uri=raw_uri,
                    page_range=annexure_payload.get("pageRange"),
                )
            )
        return records

    def _persist_artifact(self, record: AnnexureRecord, upload_info: dict) -> dict:
        collection = self._firestore.collection("artifacts")
        doc_ref = collection.document()
        payload = {
            "tenderId": record.tender_id,
            "annexureId": record.id,
            "artifactType": "annexure",
            "googleDocId": upload_info.get("id"),
            "googleDocUrl": upload_info.get("webViewLink"),
            "createdAt": firestore.SERVER_TIMESTAMP,
            "sourceRawUri": record.raw_uri,
            "pageRange": record.page_range,
        }
        doc_ref.set(payload)
        payload["id"] = doc_ref.id
        return payload

    # ------------------------------------------------------------------
    # Storage helpers
    # ------------------------------------------------------------------

    def _extract_pdf_bytes(self, record: AnnexureRecord) -> bytes:
        bucket_name, object_name = self._parse_gcs_uri(record.raw_uri)
        bucket = self._storage.bucket(bucket_name)
        blob = bucket.blob(object_name)
        if not blob.exists():
            raise RuntimeError(f"Raw annexure file {record.raw_uri} not found")
        pdf_bytes = blob.download_as_bytes()

        if record.page_range:
            start = int(record.page_range.get("start", 1))
            end = int(record.page_range.get("end", start))
            with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
                new_pdf = pikepdf.Pdf.new()
                total_pages = len(pdf.pages)
                start_idx = max(start - 1, 0)
                end_idx = min(end, total_pages)
                for page_index in range(start_idx, end_idx):
                    new_pdf.pages.append(pdf.pages[page_index])
                buffer = io.BytesIO()
                new_pdf.save(buffer)
                pdf_bytes = buffer.getvalue()

        return pdf_bytes

    @staticmethod
    def _parse_gcs_uri(uri: str) -> tuple[str, str]:
        if not uri.startswith("gs://"):
            raise ValueError(f"Unsupported URI: {uri}")
        path = uri[len("gs://") :]
        bucket, _, object_name = path.partition("/")
        if not bucket or not object_name:
            raise ValueError(f"Invalid GCS URI: {uri}")
        return bucket, object_name

    # ------------------------------------------------------------------
    # Google Drive helpers
    # ------------------------------------------------------------------

    def _upload_to_drive(self, record: AnnexureRecord, pdf_bytes: bytes) -> dict:
        service = self._drive()
        media = MediaIoBaseUpload(io.BytesIO(pdf_bytes), mimetype="application/pdf", resumable=True)
        metadata = {
            "name": f"{record.tender_id}_{record.name}.pdf",
            "mimeType": "application/vnd.google-apps.document",
        }
        if self._parent_folder_id:
            metadata["parents"] = [self._parent_folder_id]

        request = service.files().create(body=metadata, media_body=media, fields="id, webViewLink")
        return request.execute()

    def _drive(self):
        if self._drive_service is None:
            credentials, _ = google.auth.default(scopes=[
                "https://www.googleapis.com/auth/drive.file",
                "https://www.googleapis.com/auth/drive",
            ])
            self._drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        return self._drive_service
