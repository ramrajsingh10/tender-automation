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


@dataclass(frozen=True)
class OrchestratorSettings:
    base_url: str = os.environ.get("ORCHESTRATOR_BASE_URL", "")
    rag_timeout_seconds: int = int(os.environ.get("RAG_CLIENT_TIMEOUT_SECONDS", "30"))


upload_settings = UploadSettings()
storage_settings = StorageSettings()
api_settings = APISettings()
store_settings = StoreSettings()
orchestrator_settings = OrchestratorSettings()
