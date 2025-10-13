# Pipeline Orchestrator

This component coordinates the sequential → parallel → loop workflow for tender
processing. It can be implemented as a Cloud Run service backed by Cloud Workflows
or a managed task runner.

## Responsibilities

- Consume pipeline trigger messages (Pub/Sub push) emitted by the ingest service.
- Persist run state to Firestore (`pipelineRuns/{tenderId}/runs/{runId}`) with task metadata.
- Fetch the normalized document (`parsedDocuments/{tenderId}`) and forward it to task targets.
- Invoke extractor and artifact services via HTTP targets, handling retries, skips (when no endpoint configured), and QA loops.
- Update Firestore with task outcomes and surface metrics to Cloud Logging.

## Next Steps

- Decide implementation approach (Cloud Workflows vs. custom runner).
- Define task contract (`TaskRequest`, `TaskResult`) shared with extractors.
- Implement retry policies and manual override endpoints.
- Provide a QA loop handler that can surface low-confidence outputs (placeholder service lives in `services/qa_loop`).

## Local Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
uvicorn main:app --reload
```

Load environment variables before starting the service. For local testing you
can copy `config/local-services.env.example` and source it:

```bash
cp config/local-services.env.example config/local-services.env
set -a; source config/local-services.env; set +a
```

Alternatively, launch everything via Docker Compose:

```bash
cp config/docker-services.env.example config/docker-services.env
docker-compose up orchestrator extractor-deadlines extractor-emd \
  extractor-requirements extractor-penalties extractor-annexures \
  artifact-annexures qa-loop
```

### Required environment variables

| Variable | Description | Default |
| --- | --- | --- |
| `GCP_PROJECT` / `GOOGLE_CLOUD_PROJECT` | Project ID for Firestore | _(auto-detected)_ |
| `PIPELINE_COLLECTION` | Firestore collection for pipeline runs | `pipelineRuns` |
| `TENDERS_COLLECTION` | Firestore collection for tender rollups | `tenders` |
| `PARSED_COLLECTION` | Firestore collection for normalized docs | `parsedDocuments` |
| `DEADLINES_EXTRACTOR_URL` | HTTP endpoint for deadline extractor | _(required for task execution)_ |
| `EMD_EXTRACTOR_URL` | Endpoint for EMD extractor | _(optional until implemented)_ |
| `REQUIREMENTS_EXTRACTOR_URL` | Endpoint for requirements extractor | _(optional)_ |
| `PENALTIES_EXTRACTOR_URL` | Endpoint for penalties extractor | _(optional)_ |
| `ANNEXURES_EXTRACTOR_URL` | Endpoint for annexure locator | _(optional)_ |
| `ARTIFACT_ANNEXURES_URL` | Artifact builder endpoint | _(optional)_ |
| `ARTIFACT_CHECKLIST_URL` | Compliance checklist endpoint | _(optional)_ |
| `ARTIFACT_PLAN_URL` | Baseline plan endpoint | _(optional)_ |
| `RAG_INDEX_URL` | RAG indexer endpoint | _(optional)_ |
| `QA_LOOP_URL` | QA loop handler | _(optional)_ |
| `SERVICE_ENDPOINTS_JSON` | JSON map of `taskTarget -> url` overrides | _(optional)_ |
| `VERTEX_LOCATION` | Region for Vertex AI Vector Search | `us-central1` |
| `VERTEX_INDEX_ENDPOINT_ID` | Vertex AI index endpoint ID (forwarded to indexer) | `6462051937788362752` |
| `VERTEX_INDEX_ID` | Vertex AI index ID (forwarded to indexer) | `3454808470983802880` |

### Deployment

Deploy the Cloud Run service with the dedicated account
`sa-orchestrator@tender-automation-1008.iam.gserviceaccount.com` documented in
[`docs/service-accounts.md`](../../docs/service-accounts.md):

```bash
gcloud run deploy pipeline-orchestrator \
  --image gcr.io/$PROJECT_ID/pipeline-orchestrator \
  --region us-central1 \
  --service-account sa-orchestrator@tender-automation-1008.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --set-env-vars "VERTEX_LOCATION=us-central1,VERTEX_INDEX_ID=3454808470983802880,VERTEX_INDEX_ENDPOINT_ID=6462051937788362752"
```

Grant `roles/run.invoker` on downstream services to this account if you secure
their endpoints with IAM.

### Pub/Sub Push Payload Example

```bash
python scripts/simulate_pipeline.py \
  --orchestrator-url http://localhost:8000 \
  --tender-id tid-123 \
  --ingest-job-id job-abc \
  --watch
```

The helper script base64-encodes the Pub/Sub envelope and optionally watches
the pipeline run document for status updates.

## Testing

- Unit tests covering pipeline definitions live under `services/orchestrator/tests`.
