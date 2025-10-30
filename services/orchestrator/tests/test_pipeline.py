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
    expected_tasks = {task.task_id for task in DEFAULT_PIPELINE.tasks}
    assert set(run["tasks"].keys()) == expected_tasks
    for task_id, info in run["tasks"].items():
        task = next(task for task in DEFAULT_PIPELINE.tasks if task.task_id == task_id)
        assert info["stage"] == task.stage
        assert info["target"] == task.target
