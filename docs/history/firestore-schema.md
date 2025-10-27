# Firestore Data Model

> **Legacy:** This document captures the Firestore layout used by the retired
> Document AI pipeline. Refer to `docs/NewApproach.md` for the managed Vertex
> RAG workflow.

This document captures the proposed Firestore layout for the tender automation pipeline.
It assumes we operate inside the existing GCP project and reuse the `default` and
`tender-database` Firestore instances. Unless noted otherwise, each collection lives
under the `tender-database` store in native mode.

## Collections Overview

| Collection | Purpose | Primary Keys | Notes |
| --- | --- | --- | --- |
| `tenders` | Core tender metadata and status | `tenderId` (UUID as string) | Mirrors session state, enriched with pipeline rollup fields |
| `ingestJobs` | Records Eventarc-triggered ingestion runs | `jobId` (auto-id) | Links to `tenderId`, DocAI output URI, timing, status |
| `parsedDocuments` | Normalized document representation per tender | `tenderId` | Contains canonical JSON schema, attachments list, checksum |
| `pipelineRuns` | Orchestrator executions per tender | `{tenderId}/runs/{runId}` | Stores task graph status, retries, timestamps |
| `facts` | Extracted scalar data points | `auto-id` | Fields: `tenderId`, `factType`, JSON payload, confidence, provenance, `version` |
| `annexures` | Annexure descriptors + source mapping | `auto-id` | Includes `tenderId`, annexure type, page ranges, confidence, provenance, `version` |
| `plans` | Baseline project plan drafts | `auto-id` | Stores serialized task graph, schedule metadata, `version` |
| `artifacts` | References to generated files (annexures, checklists, plans) | `auto-id` | Fields: `tenderId`, `artifactType`, `annexureId`, `googleDocId`, `googleDocUrl`, source versions |
| `approvals` | BA approval states | `auto-id` | Links facts/artifacts to approval decision, approver, timestamp, before/after diff |
| `ragChunks` | RAG chunk metadata | `auto-id` | Stores chunk anchor info, embeddings index id, chunk text hash |
| `auditLogs`* | Optional manual override log | `auto-id` | Records manual pipeline actions, retries, notes |

\*Optional collection for richer auditing if Cloud Logging is insufficient.

## Document Schemas

### `tenders/{tenderId}`
```jsonc
{
  "tenderId": "d587…",
  "status": "parsing|parsed|ready-for-review|approved|published",
  "createdAt": "2024-05-18T12:30:11Z",
  "createdBy": "user@example.com",
  "sessionRef": "/sessions/d587…",     // optional back-reference to FastAPI store
  "rawBucket": "rawtenderdata",
  "parsedBucket": "parsedtenderdata",
  "latestRunId": "2024-05-18T12:30:11Z",
  "factsVersion": 3,
  "annexureVersion": 2,
  "planVersion": 1,
  "artifactVersion": 4,
  "ragIndexId": "projects/.../indexes/…",
  "lastUpdated": "2024-05-18T13:00:01Z"
}
```

### `ingestJobs/{jobId}`
```jsonc
{
  "tenderId": "d587…",
  "eventId": "storage.googleapis.com/…",
  "docAiOutputUris": ["gs://parsedtenderdata/d587/docai/output/result-0.json"],
  "rawObjectUris": ["gs://rawtenderdata/d587/original.pdf"],
  "startedAt": "2024-05-18T12:32:01Z",
  "completedAt": "2024-05-18T12:33:17Z",
  "status": "succeeded|failed|retrying",
  "error": null,
  "checksum": "sha256:…",
  "normalizedDocumentRef": "/parsedDocuments/d587"
}
```

### `parsedDocuments/{tenderId}`
```jsonc
{
  "tenderId": "d587…",
  "schemaVersion": 1,
  "documentTree": {...},        // see normalized schema spec
  "attachments": [
    {"name": "annexure-a.pdf", "contentUri": "gs://rawtenderdata/d587/...", "checksum": "sha256:…"}
  ],
  "textAnchors": {
    "0": {"page": 1, "startIndex": 0, "endIndex": 134},
    "1": {"page": 1, "startIndex": 135, "endIndex": 250}
  },
  "createdAt": "2024-05-18T12:33:17Z"
}
```

### `pipelineRuns/{tenderId}/runs/{runId}`
```jsonc
{
  "runId": "2024-05-18T12:34:00Z",
  "trigger": "eventarc|manual-retry",
  "status": "running|succeeded|failed|needs-attention",
  "tasks": {
    "normalize": {"status": "succeeded", "startedAt": "...", "completedAt": "..."},
    "extract.deadlines": {"status": "succeeded", "retries": 0},
    "extract.annexures": {"status": "failed", "retries": 2, "error": "…"},
    "qa-review": {"status": "pending"}
  },
  "createdAt": "2024-05-18T12:34:00Z",
  "completedAt": null
}
```

### `facts/{docId}`
```jsonc
{
  "tenderId": "d587…",
  "factType": "deadline.submission",
  "payload": {
    "title": "Bid Submission Deadline",
    "dueAt": "2024-06-30T17:00:00+05:30",
    "timeZone": "Asia/Kolkata"
  },
  "confidence": 0.92,
  "provenance": {
    "textAnchors": [
      {"page": 5, "startIndex": 453, "endIndex": 525}
    ],
    "sourceDoc": "gs://parsedtenderdata/d587/docai/output/result-0.json"
  },
  "version": 3,
  "createdAt": "2024-05-18T12:40:00Z",
  "createdBy": "agent.extractor.deadlines",
  "supersedes": "facts/abc123",
  "status": "pending|approved|rejected"
}
```

The `annexures`, `plans`, and `artifacts` collections follow a similar pattern: include the `tenderId`, typed payload, confidence (where applicable), provenance, `version`, `createdAt`, `createdBy`, and `supersedes`.

### `approvals/{docId}`
```jsonc
{
  "tenderId": "d587…",
  "targetType": "fact|annexure|plan|artifact",
  "targetRef": "/facts/xyz789",
  "decision": "approved|rejected|needs-clarification",
  "notes": "Deadline confirmed with procurement team.",
  "approver": "analyst@example.com",
  "createdAt": "2024-05-18T14:05:00Z",
  "changeSet": {
    "before": {...},
    "after": {...}
  },
  "linkedRunId": "2024-05-18T12:34:00Z"
}
```

### `artifacts/{docId}`
```jsonc
{
  "tenderId": "d587…",
  "artifactType": "annexure",
  "annexureId": "annexure-1",
  "googleDocId": "1AbCDefGhIjK",
  "googleDocUrl": "https://docs.google.com/document/d/1AbCDefGhIjK/edit",
  "sourceRawUri": "gs://rawtenderdata/d587/annexure-a.pdf",
  "pageRange": {"start": 12, "end": 16},
  "createdAt": "2024-05-18T14:20:00Z"
}
```

### `ragChunks/{chunkId}`
```jsonc
{
  "tenderId": "d587…",
  "chunkId": "chunk-001",
  "ragIndex": "projects/.../locations/.../indexes/...",
  "vectorId": "vec-abc",
  "textHash": "sha256:…",
  "anchor": {"page": 7, "startIndex": 1024, "endIndex": 1310},
  "section": "Technical Requirements",
  "createdAt": "2024-05-18T12:50:00Z"
}
```

## Versioning Strategy

- Each mutable document carries a monotonically increasing `version`. Superseded
  versions remain in the collection with `status = "superseded"` (or moved to a
  `/versions` subcollection) to preserve history.
- Artifacts reference the versions of facts/annexures/plans they were built from.
  Regenerating an artifact increments `artifactVersion` in `tenders/{tenderId}`.
- `approvals` documents point to the specific version they validate, ensuring edits
  post-approval trigger a new review.

## Security & Access Controls

- **Service accounts**: Ingestion, orchestrator, extractors, and artifact builders
  use dedicated service accounts with scoped Firestore roles (read/write collections
  they own). BA dashboard uses Firebase Auth backed by IAM custom claims.
- **Rules**:
  ```javascript
  service cloud.firestore {
    match /databases/{database}/documents {
      match /tenders/{tenderId} {
        allow read: if isAuthenticated();
        allow write: if isServiceAccount() || isAnalyst();
      }
      match /facts/{docId} {
        allow read: if isAuthenticated();
        allow write: if request.auth.token.role in ['extractor', 'analyst'];
      }
      match /approvals/{docId} {
        allow read: if isAnalyst();
        allow write: if isAnalyst();
      }
      // ... repeat per collection with least-privilege.
    }
  }
  ```
- **Auditing**: Firestore native audit logs capture writes; duplicate critical
  events into `auditLogs` or Cloud Logging for long-term retention.

## Relationships & Indexes

- Composite indexes required for dashboard queries:
  - `facts` on (`tenderId`, `status`, `factType`)
  - `annexures` on (`tenderId`, `status`)
  - `artifacts` on (`tenderId`, `artifactType`, `version`)
  - `approvals` on (`tenderId`, `targetType`)
- Single-field indexes for timestamps enable chronological filtering.

## Migration Plan

1. Create Firestore collections in staging with sample documents.
2. Deploy security rules with staged service account mapping.
3. Load test data via scripts to validate indexes and dashboard queries.
4. Roll out to production once extractors and dashboard integration tests pass.
