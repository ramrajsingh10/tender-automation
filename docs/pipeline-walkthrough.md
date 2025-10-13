# Pipeline Walkthrough

This guide explains how to exercise the end-to-end tender pipeline after an upload
completes and Document AI emits output files. Adapt commands to match your
environment and service URLs.

## Prerequisites

- Firestore contains a tender session and normalized document produced by the
  ingest API (`parsedDocuments/{tenderId}`).
- Raw and parsed buckets exist as defined in `docs/storage-and-events.md`.
- Pub/Sub topic wired to the orchestrator Cloud Run service (or local instance).
- Endpoint URLs (Cloud Run, Cloud Functions, or local tunnels) for each task
  target configured via the environment variables in
  `services/orchestrator/README.md` or `SERVICE_ENDPOINTS_JSON`.
- Optional: run the placeholder QA loop service locally (`services/qa_loop`).
- Copy `config/local-services.env.example` to `.env` (or equivalent) when running
  the orchestrator locally. It pre-populates localhost endpoints for the
  extractor services.
- Prefer containers? Copy `config/docker-services.env.example` to
  `config/docker-services.env` and run `docker-compose up` (or `make compose-up`).
  This launches ingest, orchestrator, all extractors, and the QA loop on the
  ports listed in the config files.

## End-to-End Exercise

1. **Upload tender package**
   - Start the frontend: `npm run web:dev`.
   - Navigate to `/tender`, upload the documents, and wait for the parsing status
     to change to *Parsed*.

2. **Confirm ingestion**
   - Inspect Firestore for `ingestJobs/{jobId}` and
     `parsedDocuments/{tenderId}`. The document should include `pages`, `tables`,
     `sections`, and `attachments` arrays.

3. **Trigger the orchestrator manually (optional)**
   - POST to the orchestrator endpoint (replace host with your deployment):

     ```bash
     python scripts/simulate_pipeline.py \
       --orchestrator-url http://127.0.0.1:8080 \
       --tender-id <TID> \
       --ingest-job-id <JOB> \
       --watch
     ```

   - The script automatically base64 encodes the Pub/Sub envelope and, when
     `--watch` is provided, polls Firestore for task status updates. Without the
     script you can still call the orchestrator directly by crafting a Pub/Sub
     envelope manually (see README).

4. **Validate extractor results**
   - After the pipeline finishes, verify:
     - `facts` collection contains deadline, EMD, requirements, and penalty
       documents tagged with `createdBy` fields like `extractor.deadlines`.
     - `annexures` collection lists annexure references produced by
       `extractor.annexures`.

5. **QA loop + retries**
   - If a service is unreachable, the orchestrator marks the task `skipped` (no
     endpoint) or `retry`/`failed`. Adjust endpoints and re-trigger as needed.
     The placeholder QA service simply acknowledges tasks; replace it when the
     manual review loop is ready.

6. **Dashboard review**
   - Use the validation workspace (frontend `/valid`) to surface facts and
     annexures once API endpoints expose them. Until then, query Firestore
     directly to confirm extracted data.
   - Navigate to `/valid?tenderId=<TID>` to fetch facts/annexures via the new
     dashboard API endpoints. Approve/Reject buttons call
     `POST /api/dashboard/facts/{id}/decision` (and the annexure equivalent)
     which update `status`, `decisionAt`, and `decisionNotes` in Firestore.

7. **Annexure artifact generation**
   - When annexures are approved, run the artifact builder service (HTTP
     `POST /generate`) by re-triggering the orchestrator or calling it directly:

     ```bash
     curl -X POST http://localhost:8106/generate \
       -H "Content-Type: application/json" \
       -d '{"tenderId":"<TID>"}'
     ```

   - The service downloads the annexure pages from Cloud Storage, uploads them as
     Google Docs (one per annexure), and records the links in Firestore
     `artifacts` collection.

8. **RAG indexing**
   - The orchestrator calls the RAG indexer (`POST /index`) to chunk the
     normalized document and push embeddings to Vertex AI Vector Search. For
     manual testing:

     ```bash
     curl -X POST http://localhost:8107/index \
       -H "Content-Type: application/json" \
       -d '{"tenderId":"<TID>","document":{...}}'
     ```

   - Embedding results are written to Firestore `ragChunks` and can be queried
     from Vertex AI for semantic retrieval.

## Troubleshooting

- Missing normalized document → ensure ingest service has write permissions to
  `parsedDocuments`.
- Tasks stuck in `retry` → inspect orchestrator logs for HTTP errors and verify
  service URLs.
- Pipeline not triggering → confirm Pub/Sub proxy has permission to call the
  orchestrator and the message payload contains `tenderId` + `ingestJobId`.
