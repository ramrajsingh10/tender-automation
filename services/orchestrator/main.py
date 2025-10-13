from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import asyncio
import httpx
from fastapi import FastAPI, HTTPException, Request, status
from google.auth import exceptions as auth_exceptions
from google.cloud import firestore
from google.cloud.firestore import Client as FirestoreClient

from pipeline import DEFAULT_PIPELINE, Task, build_pipeline_run_document

logger = logging.getLogger(__name__)


def _load_service_map() -> dict[str, str]:
    """Compile service endpoint overrides from environment variables."""
    base_map = {
        "ingest-api": os.getenv("INGEST_API_URL", ""),
        "extractor.deadlines": os.getenv("DEADLINES_EXTRACTOR_URL", ""),
        "extractor.emd": os.getenv("EMD_EXTRACTOR_URL", ""),
        "extractor.requirements": os.getenv("REQUIREMENTS_EXTRACTOR_URL", ""),
        "extractor.penalties": os.getenv("PENALTIES_EXTRACTOR_URL", ""),
        "extractor.annexures": os.getenv("ANNEXURES_EXTRACTOR_URL", ""),
        "artifact.annexures": os.getenv("ARTIFACT_ANNEXURES_URL", ""),
        "artifact.checklist": os.getenv("ARTIFACT_CHECKLIST_URL", ""),
        "artifact.plan": os.getenv("ARTIFACT_PLAN_URL", ""),
        "rag.index": os.getenv("RAG_INDEX_URL", ""),
        "qa.loop": os.getenv("QA_LOOP_URL", ""),
    }
    json_overrides = os.getenv("SERVICE_ENDPOINTS_JSON")
    if json_overrides:
        try:
            base_map.update(json.loads(json_overrides))
        except json.JSONDecodeError:
            logger.warning("Invalid SERVICE_ENDPOINTS_JSON payload; ignoring.")
    return {key: value for key, value in base_map.items() if value}


@dataclass(frozen=True)
class Settings:
    project_id: str = os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT", "")
    pipeline_collection: str = os.getenv("PIPELINE_COLLECTION", "pipelineRuns")
    tenders_collection: str = os.getenv("TENDERS_COLLECTION", "tenders")
    parsed_collection: str = os.getenv("PARSED_COLLECTION", "parsedDocuments")
    service_map: dict[str, str] = None  # type: ignore[assignment]


settings = Settings(service_map=_load_service_map())
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
            "FIRESTORE_EMULATOR_HOST before starting the orchestrator service."
        ) from exc
    return _firestore_client


def _service_endpoint(task_target: str) -> str | None:
    return (settings.service_map or {}).get(task_target)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Tender Pipeline Orchestrator",
        description="Coordinates extraction, QA, and artifact generation tasks.",
        version="0.1.0",
    )

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/pubsub/pipeline-trigger", status_code=status.HTTP_202_ACCEPTED)
    async def handle_pubsub(request: Request) -> dict[str, Any]:
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

        await _execute_pipeline(firestore_client, run_ref, run_document)

        logger.info("Queued pipeline run %s for tender %s.", run_id, tender_id)
        return {"status": "queued", "tenderId": tender_id, "runId": run_id}

    return app


app = create_app()


async def _execute_pipeline(
    firestore_client: FirestoreClient,
    run_ref: firestore.DocumentReference,
    run_document: dict[str, Any],
) -> None:
    try:
        tender_id = run_ref.parent.parent.id
        normalized_document = _load_normalized_document(firestore_client, tender_id)
    except KeyError as exc:
        run_ref.update(
            {
                "status": "failed",
                "error": str(exc),
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
        )
        return

    tasks_state = run_document["tasks"]
    current_stage = run_document["currentStage"]
    grouped = DEFAULT_PIPELINE.grouped_tasks

    while current_stage in grouped:
        stage_tasks = grouped[current_stage]
        pending = [task for task in stage_tasks if tasks_state[task.task_id]["status"] in {"pending", "retry"}]

        if not pending:
            current_stage += 1
            run_ref.update({"currentStage": current_stage, "updatedAt": datetime.now(timezone.utc).isoformat()})
            continue

        if stage_tasks[0].stage == "parallel":
            results = await _run_tasks_concurrently(run_ref, pending, normalized_document)
        else:
            results = [await _run_task(run_ref, task, normalized_document) for task in pending]

        if any(result == "failed" for result in results):
            run_ref.update({"status": "failed", "updatedAt": datetime.now(timezone.utc).isoformat()})
            return

    run_ref.update({"status": "succeeded", "updatedAt": datetime.now(timezone.utc).isoformat()})


async def _run_tasks_concurrently(
    run_ref: firestore.DocumentReference,
    tasks: list[Task],
    normalized_document: dict[str, Any],
) -> list[str]:
    async with httpx.AsyncClient(timeout=30) as client:
        coros = [_run_task(run_ref, task, normalized_document, client) for task in tasks]
        return await asyncio.gather(*coros)


async def _run_task(
    run_ref: firestore.DocumentReference,
    task: Task,
    normalized_document: dict[str, Any],
    client: httpx.AsyncClient | None = None,
) -> str:
    task_path = f"tasks.{task.task_id}"
    task_state = run_ref.get().to_dict()["tasks"][task.task_id]

    endpoint = _service_endpoint(task.target)
    if not endpoint:
        run_ref.update(
            {
                f"{task_path}.status": "skipped",
                f"{task_path}.skippedAt": datetime.now(timezone.utc).isoformat(),
                f"{task_path}.note": "No endpoint configured.",
            }
        )
        return "skipped"

    run_ref.update(
        {
            f"{task_path}.status": "in-progress",
            f"{task_path}.startedAt": datetime.now(timezone.utc).isoformat(),
        }
    )

    payload = {
        "tenderId": run_ref.parent.parent.id,
        "taskId": task.task_id,
        "target": task.target,
        "document": normalized_document,
    }

    try:
        if client is None:
            async with httpx.AsyncClient(timeout=30) as session:
                response = await session.post(endpoint, json=payload)
        else:
            response = await client.post(endpoint, json=payload)
        response.raise_for_status()
        run_ref.update({f"{task_path}.status": "succeeded", f"{task_path}.completedAt": datetime.now(timezone.utc).isoformat()})
        return "succeeded"
    except Exception as exc:
        retries = task_state.get("retries", 0) + 1
        run_ref.update(
            {
                f"{task_path}.status": "retry" if retries < 3 else "failed",
                f"{task_path}.error": str(exc),
                f"{task_path}.retries": retries,
                "status": "running",
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
        )
        return "retry" if retries < 3 else "failed"


def _load_normalized_document(firestore_client: FirestoreClient, tender_id: str) -> dict[str, Any]:
    doc = firestore_client.collection(settings.parsed_collection).document(tender_id).get()
    if not doc.exists:
        raise KeyError(f"Normalized document for tender {tender_id} not found.")
    payload = doc.to_dict()
    if not isinstance(payload, dict):
        raise KeyError(f"Normalized document for tender {tender_id} is malformed.")
    return payload
