from __future__ import annotations

from datetime import datetime, timezone

from services.orchestrator.pipeline import DEFAULT_PIPELINE, build_pipeline_run_document


def test_build_pipeline_run_document_structure():
    run = build_pipeline_run_document(
        definition=DEFAULT_PIPELINE,
        run_id="run-1",
        tender_id="tid-123",
        trigger="ingest",
        ingest_job_id="job-abc",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    assert run["runId"] == "run-1"
    assert run["tenderId"] == "tid-123"
    assert run["ingestJobId"] == "job-abc"
    assert run["status"] == "queued"
    assert "tasks" in run
    assert set(run["tasks"].keys()) == {task.task_id for task in DEFAULT_PIPELINE.tasks}
    first_task = run["tasks"]["normalize.documents"]
    assert first_task["stage"] == "sequential"
    assert first_task["target"] == "ingest-api"
    parallel_tasks = [
        task_id for task_id, info in run["tasks"].items() if info["stage"] == "parallel"
    ]
    assert "extract.deadlines" in parallel_tasks
