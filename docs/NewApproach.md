# Tender Pipeline - Managed Vertex RAG Approach

We are shifting from a custom DocAI -> chunker -> embedding pipeline to the fully managed Vertex AI workflow (Agent Builder / Vertex AI Search "RAG Engine"). This mirrors what the Vertex AI Studio "chat with documents" experience already does. Key goals:

- Offload OCR, chunking, and embeddings to Vertex AI and focus on orchestration.
- Answer questions through the same managed RAG engine the Studio uses.
- Keep uploads, validation, task assignment, and dashboards inside our tool.

---

## Phase 0 - Upload & Ingest into Agent Builder

**Objective:** Push every tender package into an Agent Builder data store (corpus).

### 0.1 Corpus setup (one-time)
- Create an Agent Builder data store in the target region (Vertex AI → Agent Builder → RAG Engines).
- Enable the Discovery Engine API and record the generated data store ID (`projects/<id>/locations/global/collections/default_collection/dataStores/<data_store>`). Populate `VERTEX_RAG_DATA_STORE_ID` and `VERTEX_RAG_SERVING_CONFIG_ID` (usually `default_serving_config`) in env files.
- Record the corpus identifiers and grant `roles/discoveryengine.admin` to the service accounts that ingest documents.
- **Current deployment:** `projects/tender-automation-1008/locations/us-east4/ragCorpora/6917529027641081856` (RAG Managed vector store backed by `text-multilingual-embedding-002`). Keep this handy for env configuration. Discovery Engine data store `projects/981270825391/locations/global/collections/default_collection/dataStores/rag_ds_useast1` and engine `projects/981270825391/locations/global/collections/default_collection/engines/tender_rag_engine_global` are provisioned with the LLM search add-on and ready for wiring. Discovery Engine still serves data stores from the `global` location; regional endpoints such as `us-east4` return 400/404, so retain the global collection IDs in configuration.

### 0.2 Tender upload workflow (per tender)
1. User uploads files; store them under `rawtenderdata/{tenderId}/` and capture status in Firestore (`tenderSessions`, `tenders/{tenderId}`).
2. Call the Agent Builder ingestion API:
   - Use `DocumentServiceClient.import_documents` with Cloud Storage URIs, or
     `FileServiceClient.upload_file` to stream bytes directly from the app.
   - Vertex handles OCR and chunking automatically. DocAI OCR becomes optional.
3. Track ingestion jobs in Firestore (`ragIngestJobs/{jobId}`) with states queued -> importing -> imported. Store generated document IDs on the tender.
4. Once imported, documents are ready for retrieval queries.

### Notes
- OCR: Agent Builder runs OCR by default. Keep DocAI only if we need field/entity extraction for downstream processes.
- Chunking/embedding: fully managed - no more `chunker.py` or manual Matching Engine upserts.
- Ingestion: `DocumentServiceClient.import_documents` must target the global data store (`projects/981270825391/locations/global/collections/default_collection/dataStores/rag_ds_useast1`). Make sure Cloud Storage URIs are accessible to the Discovery Engine service account.
- Quota: ingestion still consumes embedding quota under the hood. Watch `online_prediction_requests_per_base_model` and request increases early.
- Region note: the corpus lives in `us-east4`. Our Cloud Run services in `us-central1` will make cross-region calls until we migrate workloads or add a regional proxy.
- Cleanup: after each playbook execution we delete the imported RagFiles so the corpus is ready for the next tender.

### 0.3 Importing documents into the data store

Batch imports land all tender artifacts inside the global Discovery Engine data store so the managed engine can serve them:

```python
from google.cloud import discoveryengine_v1beta

client = discoveryengine_v1beta.DocumentServiceClient()
parent = "projects/981270825391/locations/global/collections/default_collection/dataStores/rag_ds_useast1/branches/default_branch"

operation = client.import_documents(
    request=discoveryengine_v1beta.ImportDocumentsRequest(
        parent=parent,
        gcs_source=discoveryengine_v1beta.GcsSource(
            input_uris=[f"gs://{bucket}/rawtenderdata/{tender_id}/**/*.pdf"]
        ),
        reconciliation_mode=discoveryengine_v1beta.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL,
    )
)
operation.result()  # wait for completion; status is also written to long-running operations
```

Key requirements:

- `parent` must reference the global branch—regional paths are rejected.
- The GCS bucket must grant `roles/storage.objectViewer` to the Discovery Engine service account (`service-981270825391@gcp-sa-discoveryengine.iam.gserviceaccount.com`).
- Persist the long-running operation name in Firestore (`ragIngestJobs/{jobId}`) so the orchestrator can poll until `done=true`.

For small uploads (≤10 MB) you can fall back to `FileServiceClient.upload_file`, but the branch path stays identical.

---

## Phase 1 - Question Answering via Agent Builder

**Objective:** Replace `/index/from-ocr` and the custom rag-indexer with direct calls to Agent Builder search/generative endpoints.

### 1.1 Query API integration
- Use `SearchServiceClient.search` (Vertex AI Search) whenever the BA asks a question.
  ```python
  from google.cloud import discoveryengine_v1

  search = discoveryengine_v1.SearchServiceClient()
  response = search.search(
      discoveryengine_v1.SearchRequest(
          serving_config="projects/981270825391/locations/global/collections/default_collection/dataStores/rag_ds_useast1/servingConfigs/default_serving_config",
          query="What is the submission deadline?",
      )
  )
  answers = [result.document.extracted_struct_data for result in response.results]
  ```
- The conversational API (`ConversationalSearchService`) is available for multi-turn experiences. Either way, answers include text, citations, and source documents/pages.

### 1.2 Application layer
- Build `/api/rag/query` to proxy requests to Agent Builder, store question/answer pairs in Firestore (`ragQueries/{id}`), and return answers plus citations to the UI.
- Use `/rag/playbook` on the orchestrator to import the uploaded bundle, run a curated question set, and write JSON answers to `gs://{PARSED_TENDER_BUCKET}/{tenderId}/rag/results-*.json` for the dashboard to consume.
- The validation dashboard, annexure viewer, etc., continue to read from Firestore - the only change is how data is produced.

### 1.3 Quota & throttling
- Managed RAG still uses embedding quota (`text-multilingual-embedding-002`: 5 requests per minute per project/region by default). Plan to:
  1. Request more quota via Vertex AI > Quotas.
  2. Implement retry/backoff on HTTP 429 responses or throttle to <=5 requests/min until the increase is approved.
- Monitor usage with:
  ```powershell
  gcloud alpha services quota list --consumer=projects/981270825391 --service=aiplatform.googleapis.com --format=json > quota.json
  ```
  Inspect the `text-multilingual-embedding-002` bucket in `quota.json` to see usage vs `effectiveLimit`.

---

## Phase 2 - Agent-Led Extraction & Plan Drafting

**Objective:** Retain our validation workflow but source structured data from Agent Builder instead of custom extractors.

- For each fact/annexure/plan item, run a prompt playbook:
  1. Query the RAG data store with a targeted prompt (deadlines, EMD, penalties, etc.).
  2. Parse the answer and citations.
  3. Write structured entries to Firestore (`facts`, `annexures`, `planDrafts`).
- BA validation UI continues to approve/reject entries exactly as today.

---

## Phase 3 - Validation & Drive Integration

1. BA reviews agent outputs in the validation dashboard.
2. Upon approval, Drive integration creates `Tenders/{tenderId}` folders and stores annexures, checklists, baseline plan artifacts.
3. Status updates propagate to dashboards, notifications, and the submission checklist.

---

## Phase 4 - Operational Dashboards & Task Assignment

- Dashboards display task progress, countdown timers, dependencies, and completeness scores based on the approved facts/plan records.
- BA assigns RACI roles; tasks surface to departments/partners.
- Reminders/escalations continue to trigger off Firestore state changes.

---

## Phase 5 - Submission & Pre-Flight Check

- Before submission, run the automated pre-flight checklist (validate documents, flag missing items, PII issues).
- Present a go/no-go report with outstanding gaps.
- Store supplementary artifacts (glossary, interests, stakeholder notes).

---

## Immediate Action Items

1. **Provision data store & IAM** - create the corpus, grant `discoveryengine.admin` for ingestion and `discoveryengine.user` for queries to service accounts (`sa-ingest`, backend, orchestrator`). Discovery Engine resources now exist as `rag_ds_useast1` (data store) and `tender_rag_engine_global` (engine) in the global collection; populate env vars accordingly.
1. **Ingestion wiring** - switch ingestion to `DocumentServiceClient.import_documents` pointing at `projects/981270825391/locations/global/collections/default_collection/dataStores/rag_ds_useast1/branches/default_branch`, capture operation IDs, and ensure the GCS bucket grants the Discovery Engine service account object viewer access.
1. **Serving config usage** - backend queries should call `SearchServiceClient.search` with the hard path `projects/981270825391/locations/global/collections/default_collection/dataStores/rag_ds_useast1/servingConfigs/default_serving_config` until we externalize it via configuration.
1. **Ingestion endpoint** - update the backend to call `import_documents` after each tender upload and log status in Firestore.
1. **Query proxy** - expose `/api/rag/query` to forward questions to Agent Builder and record answers/citations.
1. **Agent playbooks** - orchestrator `/rag/playbook` now runs the curated question set, writes answers to Cloud Storage, and deletes imported RagFiles after each run.
1. **Quota monitoring** - watch `text-multilingual-embedding-002` usage; throttle or request increases to avoid 429 errors.
1. **Backend wiring** - set `ORCHESTRATOR_BASE_URL` for the tender backend so it can call the orchestrator’s `/rag/query` proxy.

This document will continue to evolve as we replace legacy components. Keep it updated with technical decisions, dependencies, and open questions.

## Code Touchpoints (next up)

- `services/ingest_api`: swap Document AI hand-offs for `VertexRagDataServiceClient.import_rag_files`, accept the `VERTEX_RAG_CORPUS_*` env vars, and persist the returned document IDs.
- `services/orchestrator`: update task routing to trigger Agent Builder prompts (search/generative requests) instead of calling retired extractor endpoints.
- `frontend` API clients: confirm `/api/dashboard` and other routes expect the new answer shapes once the backend proxies Agent Builder responses.
- `services/rag-trigger-poc`: convert the hard-coded PoC into a reusable ingestion helper if we keep event-driven imports; env-ify the new corpus variables.
