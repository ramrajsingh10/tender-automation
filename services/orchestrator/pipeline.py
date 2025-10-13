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


DEFAULT_PIPELINE = PipelineDefinition(
    tasks=[
        Task(task_id="normalize.documents", stage="sequential", order=0, target="ingest-api", description="Normalize DocAI output"),
        Task(task_id="extract.deadlines", stage="parallel", order=1, target="extractor.deadlines", description="Extract deadlines"),
        Task(task_id="extract.emd", stage="parallel", order=1, target="extractor.emd", description="Extract earnest money deposits"),
        Task(task_id="extract.requirements", stage="parallel", order=1, target="extractor.requirements", description="Extract requirements"),
        Task(task_id="extract.penalties", stage="parallel", order=1, target="extractor.penalties", description="Extract penalty clauses"),
        Task(task_id="extract.annexures", stage="parallel", order=1, target="extractor.annexures", description="Locate annexures"),
        Task(task_id="qa.loop", stage="loop", order=2, target="qa.loop", description="QA and retry low-confidence outputs"),
        Task(task_id="artifact.annexures", stage="sequential", order=3, target="artifact.annexures", description="Generate annexure artifacts"),
        Task(task_id="artifact.checklist", stage="sequential", order=3, target="artifact.checklist", description="Generate compliance checklist"),
        Task(task_id="artifact.plan", stage="sequential", order=3, target="artifact.plan", description="Generate baseline plan"),
        Task(task_id="rag.index", stage="sequential", order=4, target="rag.index", description="Publish layout-aware chunks to RAG index"),
    ]
)


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
