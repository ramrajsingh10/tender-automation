# RAG Indexer Overview

The RAG indexer service converts normalized tender documents into
layout-aware chunks and stores them in Vertex AI Vector Search so downstream
applications can perform semantic retrieval.

## Inputs

- Normalized document payload (`parsedDocuments/{tenderId}`) produced by the
  ingest service. The payload contains pages, sections, tables, and text anchors
  as described in `docs/storage-and-events.md`.
- Optional list of fact IDs or section IDs to prioritise when chunking.

## Output

- Embeddings upserted to a Vertex AI Vector Search index (Matching Engine).
- Chunk metadata recorded in Firestore `ragChunks/{chunkId}` (tenderId, anchor
  references, embedding ID, text hash, section name, confidence signals).

## Chunking Strategy

1. **Sections first** – iterate over `document.sections`, extract text using the
   anchor ranges. Merge paragraphs that belong to the same section until a
   maximum token count (default 512) is reached.
2. **Tables** – flatten each table into a markdown-style representation so
   tabular data remains queryable.
3. **Fallback to page blocks** – if sections are missing, fall back to the
   `document.pages[].blocks` content.
4. Attach provenance metadata: page number, anchor IDs, section titles.

## Embedding & Upsert

- Uses Vertex AI Text Embedding model (e.g. `text-multilingual-embedding-002`) via the
  `google-cloud-aiplatform` SDK.
- Embeddings are sent to a Vector Search Index Endpoint using `upsert_datapoints`.
- Environment variables required:
  - `GCP_PROJECT`
  - `VERTEX_LOCATION`
  - `VERTEX_INDEX_ENDPOINT_ID`
  - `VERTEX_INDEX_ID`
  - `RAG_CHUNK_SIZE` (optional override for token length)

## Error Handling

- Failed chunk uploads raise a 500 error to the orchestrator; retry logic will
  reschedule the task.
- Partial success is captured in logs; chunk metadata is only written to
  Firestore after the upsert succeeds.

## Deployment Notes

- Service account must have `roles/aiplatform.user` and Firestore read/write
  permissions.
- For large tenders consider batching `upsert_datapoints` calls (default batch
  size is 100).

## Future Improvements

- Add Hybrid search (keywords + vector).
- Support automatic chunk invalidation when a tender document is reprocessed.
- Expose a retrieval endpoint for downstream applications to query the index.
