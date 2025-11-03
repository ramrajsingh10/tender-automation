# Pipeline Orchestrator

The orchestrator service runs the managed Vertex RAG playbook. It reuses RagFile
IDs produced by the ingestion worker, executes the curated question set with
Vertex RAG + Gemini, and writes timestamped JSON output to Cloud Storage. It
also exposes REST endpoints for ad-hoc queries and RagFile lifecycle management.

## Responsibilities

- Consume pipeline trigger messages (Pub/Sub push) emitted by the backend.
- Persist run state to Firestore (`pipelineRuns/{tenderId}/runs/{runId}`).
- Import tender bundles into the Vertex RAG corpus when RagFile IDs are missing.
- Execute `/rag/playbook` requests, returning answers, citations, and stored RagFile handles.
- Provide `/rag/query` for ad-hoc questions and `/rag/files/delete` for cleanup.

## Local Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
uvicorn main:app --reload
```

Load environment variables before starting the service. For local testing you
can copy `config/local-services.env.example` and source it.

Alternatively, launch everything via Docker Compose:

```bash
cp config/docker-services.env.example config/docker-services.env
docker compose up backend orchestrator ingest-worker
```

## Required environment variables

| Variable | Description | Default |
| --- | --- | --- |
| `GCP_PROJECT` / `GOOGLE_CLOUD_PROJECT` | Project ID for Firestore | _(auto-detected)_ |
| `PIPELINE_COLLECTION` | Firestore collection for pipeline runs | `pipelineRuns` |
| `TENDERS_COLLECTION` | Firestore collection for tender rollups | `tenders` |
| `PARSED_COLLECTION` | Firestore collection for normalized docs | `parsedDocuments` |
| `SERVICE_ENDPOINTS_JSON` | JSON map of `taskTarget -> url` overrides (legacy compatibility) | _(optional)_ |
| `VERTEX_RAG_CORPUS_PATH` | Vertex RAG corpus resource path | _(required)_ |
| `VERTEX_RAG_CORPUS_LOCATION` | Region for the corpus | _(required)_ |
| `VERTEX_RAG_GEMINI_MODEL` | Gemini model used for span extraction | `gemini-2.5-flash` |
| `VERTEX_RAG_CHUNK_SIZE_TOKENS` | Optional fixed-size chunking tokens applied during RagFile import | `0` (disabled) |
| `VERTEX_RAG_CHUNK_OVERLAP_TOKENS` | Optional overlap used with fixed chunking | `0` (disabled) |
| `VERTEX_RAG_CACHE_TTL_SECONDS` | TTL for in-process retrieval cache | `300` |
| `VERTEX_RAG_CACHE_MAX_ENTRIES` | Max cached retrievals held in memory | `64` |
| `VERTEX_RAG_PLAYBOOK_PACING_SECONDS` | Optional sleep between questions to smooth quota usage | `0` |
| `RAW_TENDER_BUCKET` | Bucket for raw uploads | `rawtenderdata` |
| `PARSED_TENDER_BUCKET` | Bucket for playbook output JSON | `parsedtenderdata` |

## Deployment

Deploy the Cloud Run service with the dedicated account
`sa-orchestrator@tender-automation-1008.iam.gserviceaccount.com` documented in
[`docs/service-accounts.md`](../../docs/service-accounts.md):

```bash
gcloud run deploy orchestrator \
  --source ./services/orchestrator \
  --region us-central1 \
  --service-account sa-orchestrator@tender-automation-1008.iam.gserviceaccount.com \
  --no-allow-unauthenticated
```

Grant `roles/run.invoker` on downstream services to this account if you secure
their endpoints with IAM.

## Pub/Sub Trigger Example

```bash
python scripts/simulate_pipeline.py \
  --orchestrator-url http://localhost:8080 \
  --tender-id tid-123 \
  --ingest-job-id job-abc \
  --watch
```

The helper script base64-encodes the Pub/Sub envelope and optionally watches
the pipeline run document for status updates.

## Testing

Run unit tests with:

```bash
python -m pytest services/orchestrator
```
