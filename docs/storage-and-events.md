# Storage, Events, and Normalized Document Schema

This guide specifies the storage layout, Eventarc wiring, and normalized document
contract that downstream services consume.

## Google Cloud Storage Layout

We operate with three primary buckets (names configurable via environment variables):

| Purpose | Default Bucket | Structure |
| --- | --- | --- |
| Raw document uploads | `rawtenderdata` | `/{tenderId}/{storedName}` |
| Document AI outputs | `parsedtenderdata` | `/{tenderId}/docai/output/result-{index}.json` |
| Generated artifacts | `tender-artifacts` | `/{tenderId}/{artifactType}/{version}/{fileName}` |

- **Raw uploads** hold the exact files users drop into the UI. Filenames are sanitized
  in `backend/app/routes/uploads.py` and stored with UUID prefixes.
- **Parsed outputs** contain the Document AI batch results. We keep all result shards
  for debugging. The backend records `parse.outputUri` pointing to the directory.
- **Artifacts** store annexure reproductions, compliance checklists, and baseline
  plans. Each artifact version gets a monotonically increasing number and checksum.

### Metadata Conventions

- All objects include metadata keys:
  - `tender-id`: UUID string aligning with Firestore documents.
  - `source-type`: `raw`, `docai`, `artifact`.
  - `artifact-type`: present for artifact objects (`annexure-a`, `checklist`, `plan`).
- Checksums (`crc32c` and `md5Hash`) are validated before marking uploads complete.

## Eventarc Trigger

- **Trigger**: `google.cloud.storage.object.v1.finalized` on bucket `parsedtenderdata`.
- **Filter**: object name pattern `*.json` to limit to Document AI outputs.
- **Destination**: Cloud Run service `ingest-api` (region `us-central1` unless overridden).
- **Dead-letter**: Pub/Sub topic `eventarc-ingest-dlq` for failed deliveries.

Ingest service responsibilities:
1. Confirm the object corresponds to a known `tenderId` (via metadata or path).
2. Fetch the full Document AI output set (multi-file support).
3. Emit an `ingestJobs` record and normalized document payload into Firestore.
4. Publish a message to the orchestrator queue (`projects/.../topics/tender-pipeline`).

## Normalized Document Schema

All downstream agents consume the normalized document that lives in
`parsedDocuments/{tenderId}`. The schema is versioned so we can evolve fields without
breaking extractors.

### Top-Level Structure

```jsonc
{
  "schemaVersion": 1,
  "tenderId": "d587…",
  "source": {
    "docAiOutput": ["gs://parsedtenderdata/d587/docai/output/result-0.json"],
    "rawBundle": ["gs://rawtenderdata/d587/abc.pdf"]
  },
  "document": {
    "pages": [...],
    "sections": [...],
    "tables": [...],
    "attachments": [...]
  },
  "textIndex": {
    "anchors": {...},
    "tokens": [...]
  },
  "metadata": {
    "title": "Request for Proposal – …",
    "issuingAuthority": "Department of …",
    "publishedAt": "2024-05-01",
    "language": "en",
    "ocrApplied": true
  },
  "createdAt": "2024-05-18T12:33:17Z"
}
```

#### `document.pages`

Array of pages preserving layout:
```jsonc
{
  "pageNumber": 1,
  "dimensions": {"width": 8.27, "height": 11.69, "unit": "inch"},
  "blocks": [
    {
      "type": "text",
      "anchorId": "a0001",
      "boundingPoly": [{"x": 0.12, "y": 0.10}, ...],
      "text": "Invitation for Bids …"
    },
    {
      "type": "image",
      "resource": "gs://rawtenderdata/d587/page-1-figure-1.png",
      "boundingPoly": [...]
    }
  ]
}
```

#### `document.sections`

Logical sections derived from DocAI headings and TOC cues:
```jsonc
{
  "sectionId": "sec-annexure-a",
  "title": "Annexure A – Bidder Information",
  "level": 2,
  "anchorRange": {"start": "a1050", "end": "a1350"},
  "pageRange": {"start": 23, "end": 30}
}
```

#### `document.tables`

Normalized representation with original cell text and coordinates:
```jsonc
{
  "tableId": "tbl-penalties",
  "sectionId": "sec-penalties",
  "page": 18,
  "headers": [
    {"anchorId": "a5010", "text": "Clause"},
    {"anchorId": "a5011", "text": "Penalty"}
  ],
  "rows": [
    [
      {"anchorId": "a5012", "text": "Delayed Delivery"},
      {"anchorId": "a5013", "text": "1% per week"}
    ]
  ]
}
```

#### `document.attachments`

Entries for annexures or appended docs that may require separate handling:
```jsonc
{
  "name": "Annexure B – Financial Bid Format",
  "sectionId": "sec-annexure-b",
  "pageRange": {"start": 31, "end": 35},
  "rawUri": "gs://rawtenderdata/d587/annexure-b.pdf",
  "mimeType": "application/pdf",
  "checksum": "sha256:…"
}
```

### `textIndex`

- `anchors`: map of anchor ID → `{page, startIndex, endIndex}` for quick lookup.
- `tokens`: optional array with tokenized text for search/debugging.

### Provenance

Every structural element includes anchor IDs referencing the underlying text or image
region so extractors can provide deterministic citations. Annexure reconstruction
uses the `pageRange` and `attachment` metadata to extract high-fidelity copies.

## Event Flow Summary

1. User upload → raw bucket.
2. FastAPI backend marks status and triggers DocAI batch.
3. DocAI writes JSON outputs → parsed bucket.
4. Eventarc fires to `ingest-api`.
5. Ingest normalizes data and writes Firestore documents.
6. Orchestrator consumes Firestore + Pub/Sub events to run extractors/artifact builders.
7. Outputs stored back to Firestore and artifacts bucket; dashboard consumes Firestore.

## Deployment Checklist

- Enable Eventarc service account access to parsed bucket and Cloud Run.
- Grant `ingest-api` service account read access to raw/parsed buckets and write to Firestore.
- Create Pub/Sub topic `tender-pipeline` and grant orchestrator service account publish/subscribe.
- Maintain IaC (Terraform/Google Cloud Deploy) to manage triggers, buckets, and IAM bindings.
