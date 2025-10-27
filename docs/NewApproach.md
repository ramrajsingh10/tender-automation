# Tender Pipeline - Managed Vertex RAG Blueprint

This document captures the architecture, configuration, and runbook for the managed Vertex AI RAG + Gemini implementation that replaced the legacy DocAI extractor stack. It also outlines the extensions required to reach the full product experience described in `docs/Knowledgedeck.md`.

---

## 1. System Goals
- Upload tender bundles once; reuse managed OCR, chunking, and embeddings provided by Vertex Agent Builder.
- Run deterministic playbooks that return exact citations (no regex, string search, or manual parsing).
- Keep orchestration, validation, and dashboards inside our Cloud Run + Firestore footprint.
- Provide a foundation for annexure generation, baseline project planning, and submission assurance in later phases.

---

## 2. Current High-Level Flow (MVP)
1. **Upload** - The frontend streams PDFs/DOCX to `gs://rawtenderdata/{tenderId}/...` via signed URLs issued by the backend.
2. **Ingestion** - After uploads finish, the backend calls the ingest worker (`VertexRagDataServiceClient.import_rag_files`). RagFile metadata is written to Firestore.
3. **Playbook trigger** - Once ingestion status is `done`, the backend enables `/process`. The orchestrator reuses RagFile IDs and runs the curated question set, writing answers to `gs://parsedtenderdata/{tenderId}/rag/results-*.json`.
4. **Gemini extraction** - `_run_generative_agent` retrieves contexts from Vertex RAG, prompts Gemini 2.5 Flash with the question plus raw context, and enforces exact-span answers (fallback to `NOT_FOUND`).
5. **Validation UI** - The frontend shows ingestion progress, playbook answers, citations, and RagFile handles. Users can ask ad-hoc questions via `/api/rag/query`.

---

## 3. Vertex Assets and IAM
- **Corpus**: `projects/tender-automation-1008/locations/us-east4/ragCorpora/6917529027641081856`
- **Embedding model**: `text-multilingual-embedding-002` (managed)
- **Gemini model**: `gemini-2.5-flash`
- **Service accounts**:
  - `sa-ingest@tender-automation-1008.iam.gserviceaccount.com` - `roles/discoveryengine.admin`, `roles/storage.objectViewer`, `roles/datastore.user`
  - `sa-orchestrator@tender-automation-1008.iam.gserviceaccount.com` - `roles/discoveryengine.user`, `roles/aiplatform.user`, `roles/storage.objectAdmin`, `roles/datastore.user`
  - `sa-backend@tender-automation-1008.iam.gserviceaccount.com` - `roles/storage.objectAdmin`, `roles/datastore.user`, `roles/discoveryengine.user`
- Buckets use uniform access and soft delete. Retain both `rawtenderdata` and `parsedtenderdata` so downstream automation can re-import or audit.

---

## 4. Required Environment Variables

| Variable | Description |
| -------- | ----------- |
| `VERTEX_RAG_CORPUS_LOCATION` | Corpus region (`us-east4`) |
| `VERTEX_RAG_CORPUS_PATH` | Corpus resource path |
| `VERTEX_RAG_GEMINI_MODEL` | Gemini model id (default `gemini-2.5-flash`) |
| `RAW_TENDER_BUCKET` | Bucket for uploads (`rawtenderdata`) |
| `PARSED_TENDER_BUCKET` | Bucket for playbook output (`parsedtenderdata`) |
| `INGEST_WORKER_URL` | Cloud Run URL for ingest worker |
| `INGEST_WORKER_TIMEOUT_SECONDS` | Ingest timeout (default 60) |
| `ORCHESTRATOR_BASE_URL` | Cloud Run URL for orchestrator |
| `RAG_CLIENT_TIMEOUT_SECONDS` | Orchestrator client timeout |
| `PIPELINE_COLLECTION` | Firestore pipeline runs collection |
| `TENDERS_COLLECTION` | Firestore tender sessions collection |
| `PARSED_COLLECTION` | Firestore parsed document store |

Set these variables on their respective services (backend, orchestrator, ingest worker) using Cloud Run environment configuration or secrets.

---

## 5. Orchestrator Responsibilities (`services/orchestrator/main.py`)
- Maintain Firestore pipeline state and retries when triggered via Pub/Sub (legacy hooks remain).
- Import GCS documents into the Vertex corpus when RagFile IDs are missing.
- Retrieve contexts with `VertexRagServiceClient.retrieve_contexts` and prompt Gemini for exact-span answers (`temperature=0`, `max_output_tokens=256`).
- Override Vertex Agent Builder answers with Gemini spans when present, preserving citations from the retrieved context.
- Write results to Cloud Storage (`parsedtenderdata/{tenderId}/rag/results-*.json`) and return RagFile handles to the backend.
- Expose REST endpoints:
  - `POST /rag/query`
  - `POST /rag/playbook`
  - `POST /rag/files/delete`
- Translate `GoogleAPICallError` exceptions into HTTP-friendly responses (429 for quota exhaustion, 502 for failures).

---

## 6. Ingest Worker Responsibilities (`services/ingest_worker/main.py`)
- Accept ingestion requests (`POST /ingest`) with `tenderId` and `gcsUris`.
- Update Firestore `ragIngestion` status to `running`, then `done` or `failed` depending on Vertex responses.
- Call `VertexRagDataServiceClient.import_rag_files`, wait for the long-running operation, and map RagFile names back to source URIs.
- Publish status to Pub/Sub (`INGEST_TOPIC`) when enabled.
- Return RagFile payloads so the backend can persist them immediately.

---

## 7. Backend Responsibilities (`backend/app`)
- Issue signed upload URLs, store file metadata, and trigger ingestion once all uploads finish.
- Track tender status transitions and rag ingestion metadata in Firestore.
- Proxy orchestrator endpoints for playbook execution, ad-hoc RAG queries, and RagFile deletion.
- Surface playbook output to the frontend via `/api/tenders/{id}/playbook`.
- Maintain compatibility with Firestore-backed sessions and legacy dashboard endpoints.

---

## 8. End-to-End Test Run (Manual)
1. Upload `test_data/Selection of Agency to Provide Consultants to MPSAPS.pdf` via the `/tender` UI.
2. Confirm Firestore records the tender session, file metadata, and ingestion status.
3. Wait for ingest worker to mark status `done` and note RagFile IDs.
4. Trigger `/api/tenders/{id}/process` (UI button or API call).
5. Inspect orchestrator logs; ensure retrieval and Gemini steps succeed without re-importing.
6. Open `/valid?tenderId=...` and verify:
   - Status steps show uploads, ingestion, and playbook completion.
   - Playbook answers include document identifier and submission deadlines with citations.
   - RagFile list displays the imported files.
7. Ask ad-hoc questions via "Ask the tender" to confirm `/api/rag/query` returns spans and supporting documents.

---

## 9. Extending Toward the Full Product Vision

The current pipeline covers the first third of the desired flow (upload -> extraction -> validation). To reach the complete workflow described in the knowledge deck:
- **OCR and layout enrichment** - integrate Vertex Document AI to capture table structures, signature blocks, and scanned annexures.
- **Rich data extraction** - expand prompts and structured output to cover penalties, bank guarantees, annexure lists, glossary terms, and interests.
- **Annexure/template generation** - wire Gemini function calling or document templates to build annexures automatically and store them on Drive.
- **Baseline plan automation** - codify project plan guidelines so we can generate tasks, dependencies, and compliance items on ingestion.
- **Validation workspace upgrades** - add editing, approvals, audit logs, and gating logic.
- **Google Drive automation** - call Drive API to create tender folder hierarchies post-approval.
- **Operational dashboard** - implement countdown timers, dependency graphs, status colours, and notification/escalation pipelines.
- **Pre-flight checks** - compare final uploads to the validated checklist and highlight missing signatures or incorrect formats.
- **Knowledge base** - persist glossaries and interests for future tender sourcing and analytics.

Each item is reflected in `docs/task_list.md`; treat that list as the canonical set of engineering deliverables beyond the current MVP.

---

## 10. Deployment Checklist
1. Build and deploy orchestrator:
   ```bash
   gcloud run deploy orchestrator \
     --source ./services/orchestrator \
     --region us-central1 \
     --service-account sa-orchestrator@tender-automation-1008.iam.gserviceaccount.com \
     --no-allow-unauthenticated \
     --project tender-automation-1008
   ```
2. Deploy backend and ingest worker with their respective service accounts (`sa-backend`, `sa-ingest`).
3. Update Cloud Run environment variables (Vertex corpus paths, bucket names, service URLs).
4. Deploy frontend: `firebase deploy --only hosting:tender-app`.
5. Perform a smoke test upload to confirm ingestion, playbook, and validation end-to-end.

---

## 11. Monitoring and Troubleshooting
- Check Cloud Run logs for each service (`tender-backend`, `orchestrator`, `ingest-worker`) in Cloud Logging.
- Watch Vertex AI quotas: `online_prediction_requests_per_base_model` and `generative_requests`.
- Common issues:
  - **403 when backend calls orchestrator** - ensure `ORCHESTRATOR_BASE_URL` is set and backend service account has access. Google-issued ID token audience must match the Cloud Run URL.
  - **Orchestrator warning "Skipping direct document answer due to missing project/location"** - set `GCP_PROJECT` and `VERTEX_RAG_CORPUS_LOCATION` environment variables.
  - **Vertex 429** - quota exhausted. Surface message to UI via orchestrator response and request quota increase.
  - **Frontend build ESLint error** - we run `next build --no-lint`. Leave linting for local development until Next.js 15 ESLint integration stabilises.

---

## 12. References
- `docs/Knowledgedeck.md` - holistic product narrative and roadmap.
- `docs/task_list.md` - chronological work log plus future tasks tracked against the desired flow.
- `docs/service-accounts.md` - Cloud Run service account mapping and IAM guidance.
- `docs/storage-and-events.md` - bucket structure and Pub/Sub event model.
- `docs/history/` - legacy DocAI documentation for context and regression tests.
