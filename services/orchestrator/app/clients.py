from __future__ import annotations

from typing import Any, Optional, Tuple

from google.auth import exceptions as auth_exceptions
from google.cloud import firestore, storage
from google.cloud.firestore import Client as FirestoreClient

import vertexai

try:
    from google.cloud import aiplatform_v1beta1  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    aiplatform_v1beta1 = None  # type: ignore[assignment]

from .config import settings

_firestore_client: FirestoreClient | None = None
_storage_client: storage.Client | None = None
_rag_data_client: Any | None = None
_rag_service_client: Any | None = None
_vertexai_init_context: Optional[Tuple[str, str]] = None


def get_firestore_client() -> FirestoreClient:
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client
    try:
        _firestore_client = firestore.Client(project=settings.project_id or None)
    except auth_exceptions.DefaultCredentialsError as exc:  # pragma: no cover - env misconfig
        raise RuntimeError(
            "Firestore credentials not configured. Set GOOGLE_APPLICATION_CREDENTIALS or "
            "FIRESTORE_EMULATOR_HOST before starting the orchestrator service."
        ) from exc
    return _firestore_client


def get_storage_client() -> storage.Client:
    global _storage_client
    if _storage_client is not None:
        return _storage_client
    try:
        _storage_client = storage.Client(project=settings.project_id or None)
    except auth_exceptions.DefaultCredentialsError as exc:  # pragma: no cover - env misconfig
        raise RuntimeError(
            "Google Cloud Storage credentials not configured. Set GOOGLE_APPLICATION_CREDENTIALS "
            "or STORAGE_EMULATOR_HOST before starting the orchestrator service."
        ) from exc
    return _storage_client


def get_rag_data_client():
    global _rag_data_client
    if aiplatform_v1beta1 is None:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "google-cloud-aiplatform is not installed. Add it to services/orchestrator/requirements.txt."
        )
    if not settings.vertex_rag_corpus_path:
        raise RuntimeError("VERTEX_RAG_CORPUS_PATH environment variable is not configured.")
    if _rag_data_client is not None:
        return _rag_data_client
    endpoint = None
    if settings.vertex_rag_location:
        endpoint = f"{settings.vertex_rag_location}-aiplatform.googleapis.com"
    client_options = {"api_endpoint": endpoint} if endpoint else None
    _rag_data_client = aiplatform_v1beta1.VertexRagDataServiceClient(client_options=client_options)
    return _rag_data_client


def get_rag_service_client():
    global _rag_service_client
    if aiplatform_v1beta1 is None:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "google-cloud-aiplatform is not installed. Add it to services/orchestrator/requirements.txt."
        )
    if _rag_service_client is not None:
        return _rag_service_client
    endpoint = None
    if settings.vertex_rag_location:
        endpoint = f"{settings.vertex_rag_location}-aiplatform.googleapis.com"
    client_options = {"api_endpoint": endpoint} if endpoint else None
    _rag_service_client = aiplatform_v1beta1.VertexRagServiceClient(client_options=client_options)
    return _rag_service_client


def ensure_vertexai_initialized(project_id: str, location: str) -> None:
    global _vertexai_init_context
    if _vertexai_init_context != (project_id, location):
        vertexai.init(project=project_id, location=location)
        _vertexai_init_context = (project_id, location)
