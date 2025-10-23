# Legacy Tender Pipeline (DocAI + Custom RAG)

This document captures the architecture and lessons from the original pipeline we used before moving to the managed Vertex AI RAG workflow. It is kept for future reference in case we revisit the bespoke approach.

---

## Phase Overview

### Phase 0 - Upload & Document AI Normalization
- Users uploaded files that were stored under `rawtenderdata/{tenderId}/`.
- The backend triggered the Document AI OCR processor (`6d8e1b7fa8018954`) and merged the JSON shards into one normalized document stored in Firestore (`parsedDocuments/{tenderId}`).
- We also wrote an `ingestJobs/{jobId}` entry and saved the DocAI output URIs for later stages.

### Phase 1 - Custom RAG Indexer
- A bespoke `rag-indexer` service loaded the normalized document, chunked the text, generated embeddings via Vertex AI Text Embedding 005, and upserted the vectors into Matching Engine.
- Chunk metadata was stored in Firestore (`ragChunks/{chunkId}`) for citation and validation.
- Firestore, Pub/Sub, and Cloud Run orchestrated the flow through `/index` and `/index/from-ocr` endpoints.

### Phase 2 - Agent-Led Extraction (Planned)
- The plan was to run extraction agents against the chunk store to populate facts, annexures, and baseline plan collections, then feed the validation dashboard.

---

## Why We Moved Away

- **Document size:** DocAI normalization produced enormous JSON payloads which made downstream storage and processing heavy.
- **DocAI schema drift:** The OCR processor switched to an `ocrDocument` schema, causing runtime failures until we patched the ingest service.
- **Environment configuration pain:** PowerShell mangled multi-line `--set-env-vars` commands during Cloud Run deploys, leading to restarts because the service read concatenated bucket names.
- **Vertex embedding limits:** `text-embedding-005` allows only ~20K tokens per request, so long sections triggered `INVALID_ARGUMENT` errors. We kept adjusting chunk sizes and slice averages.
- **Quota throttling:** The embedding API enforces 5 requests per minute per project/region. Chunk-heavy tenders quickly exhausted this quota, forcing us to add sleeps and retries.
- **Operational overhead:** Maintaining separate services (ingest, rag-indexer, chunker, embedding, Matching Engine) meant lots of moving pieces, IAM wiring, and troubleshooting when pipelines failed.

---

## Useful Artifacts

- **Services:** `services/ingest_api`, the now-removed `services/rag-indexer`, and the extractor services under `services/extractors`.
- **Data:** Firestore collections such as `ocrDocuments`, `ragChunks`, and related job records hold examples of the normalized payloads and chunk metadata we used.
- **Lessons:** Keep PowerShell deploy scripts simple (single-line `--set-env-vars`), always check service accounts for bucket access, set up bucket CORS for signed URLs, and monitor Vertex quotas early.

This pipeline is archived but not forgotten - refer to it if we ever need to revive the bespoke approach or study how chunking strategies affected agent performance.
