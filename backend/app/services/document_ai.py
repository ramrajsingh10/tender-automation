from __future__ import annotations

import time
from typing import Callable, Optional

import google.auth
from google.auth import exceptions as auth_exceptions
from google.auth.transport.requests import AuthorizedSession
from requests import Response

from ..settings import document_ai_settings


class DocumentAIServiceError(RuntimeError):
    """Raised when Document AI interactions fail."""


class DocumentAIService:
    def __init__(self) -> None:
        self._explicit_project_id = document_ai_settings.project_id
        self._location = document_ai_settings.location
        self._processor_id = document_ai_settings.processor_id
        self._session: AuthorizedSession | None = None
        self._project_id: str | None = self._explicit_project_id

    @property
    def is_configured(self) -> bool:
        return bool(self._processor_id and self._location)

    @property
    def project_id(self) -> str:
        if not self._project_id:
            self._ensure_session()
        if not self._project_id:
            raise DocumentAIServiceError(
                "Unable to determine Google Cloud project ID for Document AI calls."
            )
        return self._project_id

    @property
    def location(self) -> str:
        if not self._location:
            raise DocumentAIServiceError("Document AI location is not configured.")
        return self._location

    @property
    def processor_id(self) -> str:
        if not self._processor_id:
            raise DocumentAIServiceError("Document AI processor ID is not configured.")
        return self._processor_id

    def _ensure_session(self) -> AuthorizedSession:
        if self._session is None:
            try:
                credentials, default_project = google.auth.default()
            except auth_exceptions.DefaultCredentialsError as exc:
                raise DocumentAIServiceError(
                    "Google Cloud credentials not found. "
                    "Run `gcloud auth application-default login` or set "
                    "`GOOGLE_APPLICATION_CREDENTIALS`."
                ) from exc

            if not self._explicit_project_id:
                self._project_id = default_project
            else:
                self._project_id = self._explicit_project_id

            self._session = AuthorizedSession(credentials)
        return self._session

    def start_batch_process(self, input_prefix: str, output_prefix: str) -> str:
        if not self.is_configured:
            raise DocumentAIServiceError("Document AI processor is not fully configured.")

        session = self._ensure_session()
        endpoint = (
            f"https://{self.location}-documentai.googleapis.com/v1/projects/"
            f"{self.project_id}/locations/{self.location}/processors/{self.processor_id}:batchProcess"
        )
        payload = {
            "inputDocuments": {"gcsPrefix": {"gcsUriPrefix": input_prefix}},
            "documentOutputConfig": {"gcsOutputConfig": {"gcsUri": output_prefix}},
        }
        response = session.post(endpoint, json=payload, timeout=60)
        self._raise_for_error(response, "starting Document AI batch process")
        data = response.json()
        operation_name = data.get("name")
        if not operation_name:
            raise DocumentAIServiceError("Document AI response missing operation name.")
        return operation_name

    def wait_for_operation(
        self,
        operation_name: str,
        *,
        interval_seconds: int = 10,
        timeout_seconds: int = 900,
        progress_callback: Optional[Callable[[], None]] = None,
    ) -> dict:
        session = self._ensure_session()
        endpoint = f"https://{self.location}-documentai.googleapis.com/v1/{operation_name}"
        elapsed = 0

        while True:
            response = session.get(endpoint, timeout=60)
            self._raise_for_error(response, "polling Document AI operation status")
            data = response.json()
            if progress_callback:
                progress_callback()

            if data.get("done"):
                if "error" in data:
                    message = data["error"].get("message", "Document AI operation failed.")
                    raise DocumentAIServiceError(message)
                return data

            time.sleep(interval_seconds)
            elapsed += interval_seconds
            if elapsed >= timeout_seconds:
                raise DocumentAIServiceError(
                    f"Timed out waiting for Document AI operation {operation_name}."
                )

    def extract_output_uri(self, operation_response: dict) -> str | None:
        metadata = operation_response.get("metadata", {})
        statuses = metadata.get("individualProcessStatuses", [])
        for status in statuses:
            destination = status.get("outputGcsDestination")
            if destination:
                return destination
        return None

    @staticmethod
    def _raise_for_error(response: Response, context: str) -> None:
        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
            raise DocumentAIServiceError(f"Error {context}: {payload}")


document_ai_service = DocumentAIService()
