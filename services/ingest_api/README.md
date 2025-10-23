# Ingest API (Cloud Run)

> **Note:** The managed Vertex RAG pipeline invokes the orchestrator directly and
> no longer relies on this service. The Ingest API is retained as a reference for
> the legacy Document AI flow captured in `docs/OldApproach.md`.

This (legacy) service receives Eventarc notifications for Document AI output objects,
normalizes the payload, and seeds the extractor-based pipeline.

## Responsibilities

- Validate Eventarc storage events and correlate them with `tenderId`.
- Fetch Document AI JSON shards and raw documents from GCS.
- Apply OCR fallback when required and emit the normalized document schema into Firestore.
- Create an `ingestJobs` record, then publish a pipeline trigger message to Pub/Sub.

## Local Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
uvicorn main:app --reload
```

### Required environment variables

| Variable | Description | Default |
| --- | --- | --- |
| `GCP_PROJECT` / `GOOGLE_CLOUD_PROJECT` | Project ID used for Firestore and Pub/Sub | _(auto-detected)_ |
| `RAW_TENDER_BUCKET` | Bucket containing raw uploads | `rawtenderdata` |
| `PARSED_TENDER_BUCKET` | Bucket containing Document AI outputs | `parsedtenderdata` |
| `PIPELINE_TOPIC` | Pub/Sub topic (name or full path) to trigger orchestrator | _(required)_ |
| `INGEST_COLLECTION` | Firestore collection for ingest job logs | `ingestJobs` |
| `PARSED_COLLECTION` | Firestore collection for normalized docs | `parsedDocuments` |
| `TENDERS_COLLECTION` | Firestore collection for tender rollups | `tenders` |

When running locally against emulators:

```bash
export FIRESTORE_EMULATOR_HOST=localhost:8080
export PUBSUB_EMULATOR_HOST=localhost:8085
```

Example Eventarc payload for manual testing:

```bash
curl -X POST http://localhost:8000/eventarc/document-finalized \
  -H "Ce-Id=test-event" \
  -H "Ce-Type=google.cloud.storage.object.v1.finalized" \
  -H "Ce-Source=//storage.googleapis.com/projects/_/buckets/parsedtenderdata" \
  -H "Ce-Specversion=1.0" \
  -H "Ce-Subject=objects/tender123/docai/output/result-0.json" \
  -H "Content-Type=application/json" \
  -d '{"bucket":"parsedtenderdata","name":"tender123/docai/output/result-0.json"}'
```

## Deployment

Deploy to Cloud Run with the dedicated service account
`sa-ingest@tender-automation-1008.iam.gserviceaccount.com` (see
[`docs/service-accounts.md`](../../docs/service-accounts.md)) and ensure it
has permissions for:

- `roles/storage.objectViewer` on raw and parsed buckets.
- `roles/datastore.user` (Firestore access).
- `roles/pubsub.publisher` on the pipeline topic.

Example:

```bash
gcloud run deploy ingest-api \
  --image gcr.io/$PROJECT_ID/ingest-api \
  --region us-central1 \
  --allow-unauthenticated \
  --service-account sa-ingest@tender-automation-1008.iam.gserviceaccount.com
```

## Testing

- Unit tests for the ingestion handler and CloudEvent parsing are pending (`TODO`).
  Add pytest coverage once the normalization logic is implemented.
