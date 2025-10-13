from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, status
from google.auth import exceptions as auth_exceptions
from google.cloud import firestore
from google.cloud.firestore import Client as FirestoreClient

try:
    from .extractor import extract_penalties
except ImportError:
    from extractor import extract_penalties

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    project_id: str = os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT", "")
    facts_collection: str = os.getenv("FACTS_COLLECTION", "facts")


settings = Settings()
_firestore_client: FirestoreClient | None = None


def get_firestore_client() -> FirestoreClient:
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client
    try:
        _firestore_client = firestore.Client(project=settings.project_id or None)
    except auth_exceptions.DefaultCredentialsError as exc:
        raise RuntimeError(
            "Firestore credentials not configured. Set GOOGLE_APPLICATION_CREDENTIALS or "
            "FIRESTORE_EMULATOR_HOST before starting the penalties extractor."
        ) from exc
    return _firestore_client


def create_app() -> FastAPI:
    app = FastAPI(
        title="Penalties Extractor",
        description="Extracts penalty and liquidated damages clauses from normalized documents.",
        version="0.1.0",
    )

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/extract", status_code=status.HTTP_200_OK)
    async def extract(payload: dict[str, Any]) -> dict[str, Any]:
        tender_id = payload.get("tenderId")
        document = payload.get("document")
        if not tender_id or not isinstance(document, dict):
            raise HTTPException(status_code=400, detail="Invalid extractor payload.")

        facts = extract_penalties(document)
        stored_ids = _persist_facts(tender_id, facts)
        logger.info("Extracted %d penalty facts for tender %s.", len(stored_ids), tender_id)
        return {"tenderId": tender_id, "factsCreated": stored_ids}

    return app


def _persist_facts(tender_id: str, facts: list[dict[str, Any]]) -> list[str]:
    now = datetime.now(timezone.utc).isoformat()
    firestore_client = get_firestore_client()
    collection = firestore_client.collection(settings.facts_collection)
    doc_ids: list[str] = []
    for fact in facts:
        doc_ref = collection.document()
        doc = {
            "tenderId": tender_id,
            "factType": fact["factType"],
            "payload": fact["payload"],
            "confidence": fact["confidence"],
            "provenance": fact["provenance"],
            "status": "pending",
            "version": 1,
            "createdAt": now,
            "createdBy": "extractor.penalties",
        }
        doc_ref.set(doc)
        doc_ids.append(doc_ref.id)
    return doc_ids


app = create_app()
