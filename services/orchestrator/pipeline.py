from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, List


@dataclass(frozen=True)
class Task:
    task_id: str
    stage: str
    order: int
    target: str
    description: str = ""


@dataclass(frozen=True)
class PipelineDefinition:
    tasks: List[Task]

    @property
    def grouped_tasks(self) -> dict[int, list[Task]]:
        groups: dict[int, list[Task]] = {}
        for task in self.tasks:
            groups.setdefault(task.order, []).append(task)
        return groups


DEFAULT_PIPELINE = PipelineDefinition(tasks=[])


def build_pipeline_run_document(
    *,
    definition: PipelineDefinition = DEFAULT_PIPELINE,
    run_id: str,
    tender_id: str,
    trigger: str,
    ingest_job_id: str,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    timestamp = (created_at or datetime.now(timezone.utc)).isoformat()
    tasks_state = {
        task.task_id: {
            "status": "pending",
            "stage": task.stage,
            "order": task.order,
            "description": task.description,
            "target": task.target,
            "retries": 0,
        }
        for task in definition.tasks
    }
    return {
        "runId": run_id,
        "tenderId": tender_id,
        "ingestJobId": ingest_job_id,
        "trigger": trigger,
        "status": "queued",
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "tasks": tasks_state,
        "currentStage": 0,
    }
