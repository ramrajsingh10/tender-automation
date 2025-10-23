from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from requests import Response
from requests.exceptions import RequestException

from ..settings import orchestrator_settings


class RagClientError(RuntimeError):
    """Raised when the orchestrator RAG proxy cannot be reached or returns an error."""


@dataclass
class RagClient:
    base_url: str
    timeout_seconds: int = 30

    def _build_url(self, path: str) -> str:
        if not self.base_url:
            raise RagClientError(
                "ORCHESTRATOR_BASE_URL is not configured. Set it in the backend environment."
            )
        return f"{self.base_url.rstrip('/')}{path}"

    def query(
        self,
        *,
        tender_id: str,
        question: str,
        top_k: Optional[int] = None,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "tenderId": tender_id,
            "question": question,
        }
        if top_k is not None:
            payload["pageSize"] = top_k
        if conversation_id:
            payload["conversationId"] = conversation_id

        url = self._build_url("/rag/query")
        try:
            response: Response = requests.post(url, json=payload, timeout=self.timeout_seconds)
        except RequestException as exc:  # pragma: no cover - network failure
            raise RagClientError(f"Failed to reach orchestrator RAG endpoint: {exc}") from exc

        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except ValueError:  # pragma: no cover - non JSON error
                detail = response.text
            raise RagClientError(
                f"Orchestrator responded with {response.status_code}: {detail or 'unknown error'}"
            )
        try:
            return response.json()
        except ValueError as exc:  # pragma: no cover - unexpected payload
            raise RagClientError(f"Invalid JSON response from orchestrator: {exc}") from exc

    def run_playbook(
        self,
        *,
        tender_id: str,
        gcs_uris: List[str],
        questions: Optional[List[Dict[str, str]]] = None,
        forget_after_run: bool = True,
        page_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "tenderId": tender_id,
            "gcsUris": gcs_uris,
            "forgetAfterRun": forget_after_run,
        }
        if questions:
            payload["questions"] = questions
        if page_size is not None:
            payload["pageSize"] = page_size

        url = self._build_url("/rag/playbook")
        try:
            response: Response = requests.post(url, json=payload, timeout=self.timeout_seconds)
        except RequestException as exc:  # pragma: no cover
            raise RagClientError(f"Failed to reach orchestrator playbook endpoint: {exc}") from exc

        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = response.text
            raise RagClientError(
                f"Orchestrator playbook endpoint returned {response.status_code}: {detail or 'unknown error'}"
            )
        try:
            return response.json()
        except ValueError as exc:  # pragma: no cover
            raise RagClientError(f"Invalid JSON response from orchestrator playbook: {exc}") from exc


_rag_client: RagClient | None = None


def get_rag_client() -> RagClient:
    global _rag_client
    if _rag_client is None:
        _rag_client = RagClient(
            base_url=orchestrator_settings.base_url,
            timeout_seconds=orchestrator_settings.rag_timeout_seconds,
        )
    return _rag_client
