# Tender Pipeline – Gemini Vertex RAG MVP

We rebuilt the MVP to mirror the working experience in Vertex AI Studio: documents land in a managed Vertex RAG corpus and Gemini 2.5 Flash extracts exact spans from the retrieved context. This document captures the current architecture, configuration, and the runbook for an end-to-end ingest → playbook → validation cycle.

---

## 1. System Goals
- Upload tender bundles once; reuse managed OCR, chunking, and embeddings provided by Vertex AI.
- Ask deterministic playbook questions that return exact citations, not paraphrased summaries.
- Keep orchestration, validation, and dashboards inside our Cloud Run + Firestore footprint.

---

## 2. High-Level Flow
1. **Upload** – Frontend sends PDFs to the backend; files are written to `gs://rawtenderdata/{tenderId}/`.
2. **Ingestion** – The ingest service calls `VertexRagDataServiceClient.import_rag_files` against the configured corpus (`VERTEX_RAG_CORPUS_PATH`). Operation metadata and RagFile IDs are stored with the tender.
3. **Playbook trigger** – Cloud Pub/Sub notifies the orchestrator. The orchestrator imports any missing RagFiles, executes the question set, and writes answers to `gs://parsedtenderdata/{tenderId}/rag/results-*.json`.
4. **Gemini extraction** – `_run_generative_agent` fetches Vertex RAG contexts and prompts Gemini 2.5 Flash with the question plus raw context. The model must return the exact text span; we fall back to `NOT_FOUND` if nothing matches.
5. **Validation UI** – Frontend polls the backend for playbook status, streams answers with citations, and exposes an interactive “Ask the tender” panel that reuses the same RAG/Gemini path.

---

## 3. Vertex Assets & IAM
- **Corpus**: `projects/tender-automation-1008/locations/us-east4/ragCorpora/6917529027641081856`
- **Default embedding model**: managed `text-multilingual-embedding-002`
- **Gemini model**: `gemini-2.5-flash`
- **Service accounts**
  - `sa-ingest@tender-automation-1008.iam.gserviceaccount.com` – needs `roles/discoveryengine.admin` and `roles/storage.objectViewer` on the raw bucket.
  - `sa-orchestrator@tender-automation-1008.iam.gserviceaccount.com` – needs `roles/aiplatform.user`, `roles/discoveryengine.user`, and read/write access to both buckets.
  - `sa-backend@tender-automation-1008.iam.gserviceaccount.com` – needs `roles/storage.objectViewer` on `parsedtenderdata` to read result payloads.

All buckets use uniform access and soft delete. Keep `parsedtenderdata` and `rawtenderdata`; the orchestrator still writes derived artefacts.

---

## 4. Environment Variables

Add/update the following in `.env`, Secret Manager, and Cloud Run service configs:

```
VERTEX_RAG_CORPUS_LOCATION=us-east4
VERTEX_RAG_CORPUS_PATH=projects/tender-automation-1008/locations/us-east4/ragCorpora/6917529027641081856
VERTEX_RAG_GEMINI_MODEL=gemini-2.5-flash
RAW_TENDER_BUCKET=rawtenderdata
PARSED_TENDER_BUCKET=parsedtenderdata
ORCHESTRATOR_BASE_URL=https://orchestrator-<hash>.a.run.app
```

Legacy Discovery Engine data store variables remain in `.env.example` for reference, but the orchestrator now routes all retrieval through the Vertex RAG corpus.

---

## 5. Orchestrator Responsibilities (services/orchestrator/main.py)
- Maintain Firestore pipeline state and retries.
- Import PDFs into the corpus on demand via `_import_rag_files`.
- Retrieve contexts with `VertexRagServiceClient.retrieve_contexts`.
- Prompt Gemini 2.5 Flash (temperature `0.0`, `max_output_tokens=256`) and enforce exact-span answers.
- Write results to Cloud Storage and clean up transient RagFiles when `forgetAfterRun` is true.
- Expose `/rag/query` and `/rag/playbook` endpoints for the backend/UI.

---

## 6. End-to-End Test Run
Use the `test_data/` folder checked into the repo.

1. Upload a PDF through the UI or call the backend upload endpoint directly.
2. Confirm Firestore records the tender, ingest job, and RagFile IDs.
3. Trigger the orchestrator (Pub/Sub message or REST call depending on environment).
4. Inspect Cloud Run logs for `services/orchestrator`; ensure the Gemini extraction step logs contexts and answers.
5. Open the validation UI. Expect:
   - “Uploads received” and “RAG import & agent pass” checkmarks.
   - Exact values populated for `document_id` and `submission_deadlines`.
   - Citations pointing at the uploaded PDF names.
6. Repeat queries with “Ask the tender” to validate ad-hoc Q&A.

---

## 7. Deployment Checklist
1. Build and deploy the orchestrator: `gcloud builds submit --config cloudbuild.orchestrator.yaml`.
2. Deploy backend and frontend (Cloud Run + Firebase Hosting) so updated endpoints and UI are live.
3. Update secrets or service variables with the latest `VERTEX_RAG_*` values.
4. Warm up the pipeline by uploading `test_data/Selection of Agency to Provide Consultants to MPSAPS.pdf` and confirming the validation page renders answers.

---

## 8. Next Steps
- Add automated regression tests that upload a document, run the playbook, and assert the extracted text matches expected spans.
- Monitor `discoveryengine.googleapis.com/llm_requests` and `aiplatform.googleapis.com/generative_requests` quotas; request increases ahead of production launches.
- Expand the playbook once the exact-span extraction is validated.
