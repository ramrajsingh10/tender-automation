# Extractor Services

Extractor agents convert normalized documents into structured facts. Each extractor
will likely run as a containerized worker triggered by the orchestrator.

## Common Contract

- **Input**: `TaskRequest` containing `tenderId`, Firestore document references,
  and the normalized document schema.
- **Output**: `TaskResult` with structured payloads, confidence scores, and
  provenance anchors suitable for insertion into Firestore.

## Planned Extractors

1. `deadlines` – submission, pre-bid, clarification timelines.  
2. `emd` – earnest money deposit / upfront costs.  
3. `requirements` – technical and financial criteria.  
4. `penalties` – liquidated damages and penalty clauses.  
5. `annexures` – locate annexure sections and metadata for reconstruction.

Each extractor should include deterministic parsing logic, fallback heuristics,
and optional LLM assistance gated behind confidence thresholds.

## Development Workflow

- Shared utility library (`services/extractors/lib`) will expose helper modules for
  text-anchor handling, regex templates, and Firestore writes (TODO).
- Unit tests should consume recorded DocAI outputs stored under `tests/fixtures/`.
- When developing without cloud credentials, point the services at the Firestore emulator by
  setting `FIRESTORE_EMULATOR_HOST`; the lazy client helpers will reuse that configuration.

## Deployment

Cloud Run deployments must use the scoped service accounts defined in
[`docs/service-accounts.md`](../../docs/service-accounts.md). Each extractor only
needs Firestore access, so the accounts are limited to `roles/datastore.user`.

| Cloud Run Service | Service Account |
| --- | --- |
| `extractor-deadlines` | `sa-extractor-deadlines@tender-automation-1008.iam.gserviceaccount.com` |
| `extractor-emd` | `sa-extractor-emd@tender-automation-1008.iam.gserviceaccount.com` |
| `extractor-requirements` | `sa-extractor-requirements@tender-automation-1008.iam.gserviceaccount.com` |
| `extractor-penalties` | `sa-extractor-penalties@tender-automation-1008.iam.gserviceaccount.com` |
| `extractor-annexures` | `sa-extractor-annexures@tender-automation-1008.iam.gserviceaccount.com` |

Example deployment:

```bash
gcloud run deploy extractor-deadlines \
  --image gcr.io/$PROJECT_ID/extractor-deadlines \
  --region us-central1 \
  --service-account sa-extractor-deadlines@tender-automation-1008.iam.gserviceaccount.com \
  --no-allow-unauthenticated
```
