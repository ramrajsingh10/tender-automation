from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import FastAPI, HTTPException, Request, status
from google.api_core import exceptions as google_exceptions
from google.cloud import firestore

from pipeline import DEFAULT_PIPELINE, build_pipeline_run_document

from .clients import get_firestore_client
from .config import settings
from .generative import generate_document_answer, has_substantive_answer
from .models import (
    RagDeleteRequest,
    RagPlaybookRequest,
    RagPlaybookResponse,
    RagQueryRequest,
    RagQueryResponse,
    RagAnswer,
)
from .pipeline_runner import execute_pipeline
from .playbook import run_playbook, filter_structured_entries, format_structured_entries
from .rag import (
    delete_rag_files,
    execute_vertex_search,
    map_rag_files_by_uri,
    populate_answer_evidence,
    supplement_answer_evidence_from_contexts,
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Tender Pipeline Orchestrator",
        description="Coordinates managed Vertex RAG playbook execution.",
        version="0.1.0",
    )

    @app.get("/healthz", tags=["meta"])
    def healthz() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/rag/query", tags=["rag"])
    async def rag_query(request: RagQueryRequest) -> RagQueryResponse:
        if not settings.vertex_rag_corpus_path:
            raise HTTPException(
                status_code=503,
                detail="Vertex RAG corpus is not configured. Set VERTEX_RAG_CORPUS_PATH.",
            )
        try:
            payload, contexts = execute_vertex_search(request)
        except google_exceptions.ResourceExhausted as exc:
            logger.warning("RAG query quota exhausted for tender %s: %s", request.tenderId, exc)
            raise HTTPException(
                status_code=429,
                detail="Vertex RAG embedding quota exhausted. Retry later or request a quota increase.",
            ) from exc
        except google_exceptions.GoogleAPICallError as exc:
            logger.exception("Vertex RAG query failed for tender %s.", request.tenderId)
            raise HTTPException(status_code=502, detail=f"Vertex Agent Builder query failed: {exc}") from exc
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("RAG query failed for tender %s.", request.tenderId)
            raise HTTPException(status_code=502, detail=f"Vertex Agent Builder query failed: {exc}") from exc

        gcs_uris: List[str] = list(request.gcsUris or [])
        if not gcs_uris and request.ragFileIds:
            mapping = map_rag_files_by_uri()
            wanted = set(request.ragFileIds)
            for uri, name in mapping.items():
                if name in wanted:
                    gcs_uris.append(uri)

        structured_entries, raw_text = generate_document_answer(request.question, gcs_uris, mode="freeform")
        filtered_entries = filter_structured_entries("ad_hoc", structured_entries)

        if filtered_entries:
            formatted_text = format_structured_entries(filtered_entries)
            payload.answers = [
                RagAnswer(
                    text=formatted_text,
                    citations=[],
                )
            ]
        elif raw_text:
            cleaned_text = raw_text.strip().strip("`").strip()
            payload.answers = [
                RagAnswer(
                    text=cleaned_text or "No relevant context found.",
                    citations=[],
                )
            ]
        elif not has_substantive_answer(payload.answers or []):
            payload.answers = [RagAnswer(text="No relevant context found.", citations=[])]

        populate_answer_evidence(payload.answers, payload.documents)
        supplement_answer_evidence_from_contexts(payload.answers, contexts)
        return payload

    @app.post("/rag/playbook", tags=["rag"])
    async def rag_playbook(request: RagPlaybookRequest) -> RagPlaybookResponse:
        if not request.gcsUris and not request.ragFileIds:
            raise HTTPException(
                status_code=400,
                detail="Provide either gcsUris to import or ragFileIds to reuse existing RagFiles.",
            )
        try:
            response = run_playbook(request)
        except google_exceptions.ResourceExhausted as exc:
            logger.warning("Playbook quota exhausted for tender %s: %s", request.tenderId, exc)
            raise HTTPException(
                status_code=429,
                detail="Vertex RAG embedding quota exhausted. Retry later or request a quota increase.",
            ) from exc
        except google_exceptions.GoogleAPICallError as exc:
            logger.exception("Playbook execution failed for tender %s.", request.tenderId)
            raise HTTPException(status_code=502, detail=f"Failed to run playbook: {exc}") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Playbook execution failed for tender %s.", request.tenderId)
            raise HTTPException(status_code=502, detail=f"Failed to run playbook: {exc}") from exc
        return response

    @app.post("/rag/files/delete", tags=["rag"])
    async def rag_files_delete(request: RagDeleteRequest) -> Dict[str, List[str]]:
        if not request.ragFileIds:
            raise HTTPException(status_code=400, detail="ragFileIds must not be empty.")
        deleted, errors = delete_rag_files(request.ragFileIds)
        return {"deleted": deleted, "errors": errors}

    @app.post("/pubsub/pipeline-trigger", status_code=status.HTTP_202_ACCEPTED)
    async def handle_pubsub(request: Request) -> Dict[str, str]:
        payload = await request.json()
        message = payload.get("message")
        if not message or "data" not in message:
            raise HTTPException(status_code=400, detail="Invalid Pub/Sub message payload.")
        try:
            data_bytes = base64.b64decode(message["data"])
            trigger_payload = json.loads(data_bytes)
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Failed to decode Pub/Sub message.") from exc
        tender_id = trigger_payload.get("tenderId")
        ingest_job_id = trigger_payload.get("ingestJobId")
        if not tender_id or not ingest_job_id:
            raise HTTPException(status_code=400, detail="Missing tenderId or ingestJobId in message.")

        run_id = datetime.now(timezone.utc).isoformat()
        run_document = build_pipeline_run_document(
            definition=DEFAULT_PIPELINE,
            run_id=run_id,
            tender_id=tender_id,
            trigger=trigger_payload.get("trigger", "ingest"),
            ingest_job_id=ingest_job_id,
        )
        firestore_client = get_firestore_client()
        pipeline_doc = firestore_client.collection(settings.pipeline_collection).document(tender_id)
        now = datetime.now(timezone.utc).isoformat()
        pipeline_doc.set(
            {
                "tenderId": tender_id,
                "latestRunId": run_id,
                "updatedAt": now,
            },
            merge=True,
        )
        run_ref = pipeline_doc.collection("runs").document(run_id)
        run_ref.set(run_document)
        firestore_client.collection(settings.tenders_collection).document(tender_id).set(
            {"tenderId": tender_id, "pipelineRunId": run_id, "lastUpdated": now},
            merge=True,
        )
        await execute_pipeline(firestore_client, run_ref, run_document)
        logger.info("Queued pipeline run %s for tender %s.", run_id, tender_id)
        return {"status": "queued", "tenderId": tender_id, "runId": run_id}

    return app
