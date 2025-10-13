"""Utility script to trigger the orchestrator and optionally watch task progress."""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from typing import Any

import requests
from google.cloud import firestore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trigger the tender pipeline orchestrator.")
    parser.add_argument("--orchestrator-url", required=True, help="Base URL for the orchestrator service.")
    parser.add_argument("--tender-id", required=True, help="Tender identifier to process.")
    parser.add_argument("--ingest-job-id", required=True, help="Ingest job ID associated with the tender.")
    parser.add_argument(
        "--project",
        default=None,
        help="Firestore project ID (defaults to environment configuration).",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Poll Firestore for pipeline status after triggering.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.5,
        help="Polling interval in seconds when --watch is enabled.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Stop watching after this many seconds when --watch is enabled.",
    )
    return parser.parse_args()


def trigger_orchestrator(orchestrator_url: str, tender_id: str, ingest_job_id: str) -> dict[str, Any]:
    payload = {"tenderId": tender_id, "ingestJobId": ingest_job_id}
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    envelope = {"message": {"data": encoded}}

    response = requests.post(
        f"{orchestrator_url.rstrip('/')}/pubsub/pipeline-trigger",
        json=envelope,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def watch_pipeline(
    tender_id: str,
    run_id: str,
    project: str | None,
    interval: float,
    timeout: float,
) -> None:
    client = firestore.Client(project=project)
    run_ref = (
        client.collection("pipelineRuns")
        .document(tender_id)
        .collection("runs")
        .document(run_id)
    )

    deadline = time.monotonic() + timeout
    last_status = None

    while time.monotonic() < deadline:
        snapshot = run_ref.get()
        if not snapshot.exists:
            print("Pipeline run document not found yet...")
            time.sleep(interval)
            continue
        data = snapshot.to_dict()
        status = data.get("status")
        if status != last_status:
            print(f"[{time.strftime('%H:%M:%S')}] status={status}")
            last_status = status
        tasks = data.get("tasks", {})
        for task_id, info in tasks.items():
            print(f"  - {task_id}: {info.get('status')} (retries={info.get('retries')})")
        if status in {"succeeded", "failed"}:
            return
        time.sleep(interval)

    print("Watch timed out without terminal status.")


def main() -> None:
    args = parse_args()
    try:
        response = trigger_orchestrator(args.orchestrator_url, args.tender_id, args.ingest_job_id)
    except requests.HTTPError as exc:
        print(f"Failed to trigger orchestrator: {exc} ({getattr(exc.response, 'text', '')})", file=sys.stderr)
        sys.exit(1)

    run_id = response.get("runId")
    print(f"Triggered pipeline run {run_id} for tender {args.tender_id}")

    if args.watch and run_id:
        try:
            watch_pipeline(args.tender_id, run_id, args.project, args.interval, args.timeout)
        except Exception as exc:  # pragma: no cover - logging convenience
            print(f"Error watching pipeline: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
