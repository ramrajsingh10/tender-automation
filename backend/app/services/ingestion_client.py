from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from requests import Response
from requests.exceptions import RequestException

from google.auth.transport.requests import Request
from google.oauth2 import id_token

from ..settings import ingestion_settings


class IngestionClientError(RuntimeError):
    """Raised when the ingestion worker cannot be reached or returns an error."""


@dataclass
class IngestionClient:
    base_url: str
    timeout_seconds: int = 60

    def _build_url(self, path: str) -> str:
        if not self.base_url:
            raise IngestionClientError(
                "INGEST_WORKER_URL is not configured. Set it before triggering ingestion."
            )
        return f"{self.base_url.rstrip('/')}{path}"

    def start_ingestion(self, *, tender_id: str, gcs_uris: List[str]) -> Dict[str, Any]:
        if not gcs_uris:
            raise IngestionClientError("No Cloud Storage URIs were provided for ingestion.")
        payload: Dict[str, Any] = {
            "tenderId": tender_id,
            "gcsUris": gcs_uris,
        }
        url = self._build_url("/ingest")
        headers: Dict[str, str] = {}
        audience = self.base_url.rstrip("/")

        try:
            auth_request = Request()
            token = id_token.fetch_id_token(auth_request, audience)
            headers["Authorization"] = f"Bearer {token}"
        except Exception as exc:  # pragma: no cover - auth bootstrap failure
            raise IngestionClientError(f"Failed to obtain ID token for ingestion worker: {exc}") from exc
        try:
            response: Response = requests.post(url, json=payload, headers=headers, timeout=self.timeout_seconds)
        except RequestException as exc:  # pragma: no cover - network failure
            raise IngestionClientError(f"Failed to reach ingestion worker: {exc}") from exc

        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = response.text
            raise IngestionClientError(
                f"Ingestion worker responded with {response.status_code}: {detail or 'unknown error'}"
            )

        try:
            return response.json()
        except ValueError as exc:  # pragma: no cover - unexpected payload
            raise IngestionClientError(f"Invalid JSON response from ingestion worker: {exc}") from exc


_ingestion_client: Optional[IngestionClient] = None


def get_ingestion_client() -> IngestionClient:
    global _ingestion_client
    if _ingestion_client is None:
        _ingestion_client = IngestionClient(
            base_url=ingestion_settings.worker_url,
            timeout_seconds=ingestion_settings.timeout_seconds,
        )
    return _ingestion_client
