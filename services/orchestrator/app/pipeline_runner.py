from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
from google.cloud import firestore
from google.cloud.firestore import Client as FirestoreClient

from pipeline import DEFAULT_PIPELINE, Task

from .config import settings


async def execute_pipeline(
    firestore_client: FirestoreClient,
    run_ref: firestore.DocumentReference,
    run_document: Dict[str, Any],
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
    tasks: List[Task],
    normalized_document: Dict[str, Any],
) -> List[str]:
    async with httpx.AsyncClient(timeout=30) as client:
        coroutines = [_run_task(run_ref, task, normalized_document, client) for task in tasks]
        return await asyncio.gather(*coroutines)


async def _run_task(
    run_ref: firestore.DocumentReference,
    task: Task,
    normalized_document: Dict[str, Any],
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
    except Exception as exc:  # pragma: no cover - external dependency
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


def _load_normalized_document(firestore_client: FirestoreClient, tender_id: str) -> Dict[str, Any]:
    doc = firestore_client.collection(settings.parsed_collection).document(tender_id).get()
    if not doc.exists:
        raise KeyError(f"Normalized document for tender {tender_id} not found.")
    payload = doc.to_dict()
    if not isinstance(payload, dict):
        raise KeyError(f"Normalized document for tender {tender_id} is malformed.")
    return payload


def _service_endpoint(task_target: str) -> str | None:
    return (settings.service_map or {}).get(task_target)

