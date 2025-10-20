# New Tender Pipeline Approach (OCR + RAG)

This document captures the revised architecture for the tender automation system.  
We are moving away from heavyweight Document AI normalized documents and adopting
an OCR-first pipeline that feeds a Retrieval-Augmented Generation (RAG) layer and
LLM-driven agents. The primary goals are to reduce payload bloat, simplify data
flows, and enable flexible AI reasoning over tender content.

---

## Phase 0 – Upload & OCR Ingestion

**Objective:** Replace the existing Document AI “specialized parser” stage with the
Document OCR processor (`6d8e1b7fa8018954` in region `us`) and persist results in a
chunk-friendly format.

1. **User upload (unchanged)**
   - Files land in `rawtenderdata/{tenderId}/`.
   - Upload status is tracked in Firestore (`tenderSessions`, `tenders/{tenderId}`).

2. **Trigger OCR**
   - Backend calls the OCR processor using the prediction endpoint  
     `https://us-documentai.googleapis.com/.../processors/6d8e1b7fa8018954:process`.
   - Store OCR output (per-page text + layout metadata) in  
     `parsedtenderdata/{tenderId}/ocr/{page}.json` or an equivalent structure.

3. **Emit ingestion event**
   - Write a concise record to Firestore (`ocrJobs/{jobId}`) and publish a Pub/Sub
     message so downstream indexing can start.

_No normalization step is created; the large monolithic document is intentionally
skipped._

---

## Phase 1 – RAG Indexing

**Objective:** Chunk OCR text and index it for semantic retrieval.

Implementation highlights:

1. The RAG indexer now exposes two endpoints:
   - `POST /index` (legacy path) accepts a document payload.
   - `POST /index/from-ocr` loads the OCR document from Firestore
     (`ocrDocuments/{tenderId}`) and handles chunking internally.
2. `chunk_document` understands OCR-style `pages` with raw text and breaks them
   into page/paragraph sized chunks (~1200 characters by default).
3. Chunks are embedded (Vertex AI Text Embedding 005) and upserted to
   Matching Engine.
4. Chunk metadata is persisted to Firestore (`ragChunks/{chunkId}`) including
   page numbers and detected languages for later prompts.
5. The service is ready to be invoked automatically once Phase 0 stores OCR
   output. Manual testing can be done via curl:

   ```bash
   curl -X POST https://<rag-indexer-url>/index/from-ocr \
     -H "Content-Type: application/json" \
     -d '{"tenderId":"<TID>"}'
   ```

6. Next steps for Phase 1:
   - Wire a trigger (Cloud Task, Pub/Sub, or orchestrator call) so that each
     stored OCR job invokes `/index/from-ocr`.
   - Record the resulting index identifier (if needed) on `tenders/{tenderId}`.

---

## Phase 2 – Agent-Led Extraction & Plan Drafting

**Objective:** Replace deterministic extractors with LLM-driven playbooks that use
RAG to answer questions and produce structured outputs.

Tasks processed via agent prompts:

- Critical dates (submission, pre-bid, clarifications, etc.).
- Financial data (EMD, fee schedules).
- Technical & financial requirements.
- Penalties / liquidated damages.
- Annexure references and page ranges.
- Compliance checklist items.
- Baseline project plan (deadline-driven, requirement-based, compliance tasks).

Each agent call writes structured results to Firestore collections (`facts`,
`annexures`, `planDrafts`/`artifacts`). Human analysts review the data via the
existing validation dashboard.

---

## Phase 3 – Validation & Drive Integration

1. The BA validates facts/annexures/plan items in the dashboard.
2. Upon approval, Google Drive folders are created under `Tenders/{tenderId}` with
   subfolders for annexures, departments, and plan artifacts.
3. Annexure PDFs and generated documents are stored via the artifact builder.

---

## Phase 4 – Operational Dashboards & Task Assignment

1. Approved data populates central dashboards (progress colors, dependencies,
   countdown timers, completeness score).
2. The BA assigns ownership using the RACI matrix; tasks are synced to Firestore
   and surfaced to partners with appropriate access controls.
3. Notifications and escalations are triggered based on task status.

---

## Phase 5 – Submission & Pre-Flight Check

1. Before submission, the BA runs a pre-flight checklist comparing validated data
   with uploaded documents.
2. The system flags missing files, incorrect formats, unsigned forms, and presents
   a go/no-go report.
3. Additional artifacts (glossary, stakeholder interests) are generated and stored.

---

## Future Enhancements

- Automated tender ingestion from public sources.
- Auto-RACI assignment once org charts and partner lists are standardized.
- Secure external partner portal with scoped task visibility.
- Automatic generation of annexure-specific documents (e.g., CVs) in the required
  format.
- Win/loss tracking linked to plan execution.

---

## Immediate Action Items

1. **Automate OCR → RAG trigger** – invoke `/index/from-ocr` whenever an OCR job
   transitions to `stored`.
2. **Agent skeleton** – define prompt templates for deadlines, requirements, and
   penalties; write results to Firestore.
3. **Dashboard alignment** – ensure validation UI consumes the new Firestore schema
   (facts, annexures, plan drafts) generated by agents.

This document will evolve as each phase is implemented. Keep it up to date with
technical decisions, deliverables, and open questions.
