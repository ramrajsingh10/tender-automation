# Storage, Agent Outputs, and Event Flow (Managed RAG)

This document captures the storage layout and runtime flow for the new
managed Vertex RAG pipeline. The previous Document AI normalization
details now live in `docs/OldApproach.md`.

## Google Cloud Storage Layout

We operate with three primary buckets (names remain configurable through
environment variables):

| Purpose | Default Bucket | Structure |
| --- | --- | --- |
| Raw document uploads | `rawtenderdata` | `/{tenderId}/{storedName}` |
| Vertex RAG playbook results | `parsedtenderdata` | `/{tenderId}/rag/results-YYYYMMDDThhmmssZ.json` |
| Generated artifacts (optional) | `tender-artifacts` | `/{tenderId}/{artifactType}/{version}/{fileName}` |

- **Raw uploads** hold the exact files users submit via the UI. Filenames are
  sanitized and stored with UUID prefixes in `backend/app/routes/uploads.py`. Multiple
  documents per tender are allowed.
- **RAG results** contain the JSON emitted by the orchestrator after running the
  managed Vertex AI playbook. Filenames are timestamped so each run is preserved.
  The backend records `parse.outputUri` pointing at the most recent JSON file.
- **Artifacts** continue to store annexure reproductions, compliance checklists,
  and other generated deliverables. These are optional in the new flow.

## Vertex RAG Playbook Output

Each JSON file written under `gs://parsedtenderdata/{tenderId}/rag/` follows this shape:

```jsonc
{
  "tenderId": "827b7205-e857-400b-bdc4-12c79849db36",
  "generatedAt": "2025-10-22T13:45:07Z",
  "results": [
    {
      "questionId": "submission_deadline",
      "question": "What is the submission deadline for this tender? Include date and time if specified.",
      "answers": [
        {
          "text": "Bids must be submitted by 12 November 2025 at 3:00 PM IST.",
          "citations": [
            {
              "startIndex": 42,
              "endIndex": 93,
              "sources": [
                {
                  "reference": {
                    "document": "projects/.../ragCorpora/.../ragFiles/123",
                    "title": "Section 4: Submission Instructions",
                    "uri": "gs://rawtenderdata/827b7205-e857-400b-bdc4-12c79849db36/tender.pdf",
                    "chunkContents": [
                      {"content": "Submissions are due by 12 November 2025 at 15:00 hrs IST.", "pageIdentifier": "Page 9"}
                    ]
                  }
                }
              ]
            }
          ]
        }
      ],
      "documents": [
        {
          "id": "projects/.../documents/456",
          "title": "Submission Instructions",
          "snippet": "Proposals must be submitted no later than 12 November 2025, 3:00 PM IST",
          "uri": "gs://rawtenderdata/.../tender.pdf"
        }
      ]
    }
  ]
}
```

The frontend validation workspace and backend `GET /api/tenders/{tenderId}/playbook`
endpoint surface this data directly.

## Event Flow Summary

1. **Upload:** The user drops one or more files in the UI. Files land in
   `gs://rawtenderdata/{tenderId}/`.
2. **Trigger:** When the BA clicks “Process”, the backend calls the orchestrator’s
   `/rag/playbook` endpoint with the list of raw GCS URIs.
3. **Vertex RAG import & questions:** The orchestrator
   - Imports the raw bundle into the configured `ragCorpora` using the
     Vertex Rag Data API,
   - Executes the curated question set (`DEFAULT_PLAYBOOK`) via Discovery Engine
     search,
   - Writes the JSON payload shown above to `parsedtenderdata/{tenderId}/rag/`,
   - Deletes the imported RagFiles so the corpus is clean for the next run.
4. **Surfacing results:** The backend updates the tender session status to `parsed`
   and records the `parse.outputUri`. The validation UI reads the JSON for review,
   and the BA can re-run the playbook at any time.

### Multi-file Tenders

The orchestrator imports every `gs://rawtenderdata/{tenderId}/{storedName}` supplied
in the request. Vertex Agent Builder chunking handles the combined corpus, so answers
reflect all uploaded documents.

### Legacy Document AI Flow

The original Document AI normalization pipeline and Firestore schema are preserved
for reference in `docs/OldApproach.md`. No new data is written to `docai/output/`
under the managed RAG workflow.
