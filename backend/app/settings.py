from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class UploadSettings:
    max_file_size_bytes: int = 5 * 1024 * 1024  # 5 MB
    allowed_mime_types: tuple[str, ...] = (
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    max_files: int | None = None


@dataclass(frozen=True)
class StorageSettings:
    raw_bucket: str = os.environ.get("RAW_TENDER_BUCKET", "rawtenderdata")
    parsed_bucket: str = os.environ.get("PARSED_TENDER_BUCKET", "parsedtenderdata")
    signed_url_expiration_seconds: int = int(os.environ.get("SIGNED_URL_EXPIRATION_SECONDS", "900"))


@dataclass(frozen=True)
class DocumentAISettings:
    project_id: str = os.environ.get("GCP_PROJECT_ID", "")
    location: str = os.environ.get("DOCUMENT_AI_LOCATION", "us")
    processor_id: str = os.environ.get("DOCUMENT_AI_PROCESSOR_ID", "")


@dataclass(frozen=True)
class APISettings:
    allowed_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.environ.get("API_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ) or ("*",)


@dataclass(frozen=True)
class StoreSettings:
    backend: str = os.environ.get("STORE_BACKEND", "memory").lower()
    firestore_collection: str = os.environ.get("FIRESTORE_COLLECTION", "tenderSessions")


upload_settings = UploadSettings()
storage_settings = StorageSettings()
document_ai_settings = DocumentAISettings()
api_settings = APISettings()
store_settings = StoreSettings()
