# Storage, Agent Outputs, and Event Flow (Managed RAG)

This document captures the storage layout and runtime flow for the current managed Vertex RAG pipeline. Legacy Document AI notes remain in `docs/history/OldApproach.md`.

## Google Cloud Storage Layout

Three primary buckets (names remain configurable via environment variables):

| Purpose | Default Bucket | Structure |
| --- | --- | --- |
| Raw document uploads | `rawtenderdata` | `/{tenderId}/{storedName}` |
| Vertex RAG playbook results | `parsedtenderdata` | `/{tenderId}/rag/results-YYYYMMDDThhmmssZ.json` |
| Generated artefacts (future) | `tender-artifacts` | `/{tenderId}/{artifactType}/{version}/{fileName}` |

- **Raw uploads** hold the exact files submitted via the UI. Filenames are sanitised and stored with UUID prefixes in `backend/app/routes/uploads.py`.
- **RAG results** contain the JSON emitted by the orchestrator after running the managed Vertex AI playbook. Filenames are timestamped so each run is preserved. The backend records `parse.outputUri` pointing at the latest JSON file.
- **Artefacts** will store annexures, checklists, and generated plans once those services come online.

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
              "sources": [
                {
                  "reference": {
                    "document": "projects/.../ragCorpora/.../ragFiles/123",
                    "title": "Section 4: Submission Instructions",
                    "uri": "gs://rawtenderdata/827b7205-e857-400b-bdc4-12c79849db36/tender.pdf",
                    "chunkContents": [
                      {
                        "content": "Submissions are due by 12 November 2025 at 15:00 hrs IST.",
                        "pageIdentifier": "Page 9"
                      }
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

The frontend validation workspace and backend `GET /api/tenders/{tenderId}/playbook` endpoint surface this data directly.

## Event Flow Summary

1. **Upload** - The user drops one or more files in the UI. Files land in `gs://rawtenderdata/{tenderId}/`.
2. **Trigger** - When "Process" is clicked (or automatically after ingestion completes in future iterations), the backend calls the orchestrator `/rag/playbook` endpoint once ingestion reports status `done`.
3. **Vertex RAG import and questions** - The orchestrator:
   - Imports the raw bundle into the configured corpus when RagFile IDs are missing.
   - Executes the curated question set via Vertex RAG retrieval and Gemini extraction.
   - Writes the JSON payload above to `parsedtenderdata/{tenderId}/rag/`.
   - Returns RagFile handles to the backend so they can be reused on subsequent runs.
4. **Surfacing results** - The backend updates the tender session status to `parsed` and records the `parse.outputUri`. The validation UI reads the JSON for review, and the BA can re-run the playbook at any time. A delete action triggers `/rag/files/delete` if the operator wants to remove RagFiles after validation.

### Multi-file Tenders

The orchestrator imports every `gs://rawtenderdata/{tenderId}/{storedName}` supplied in the request. Vertex Agent Builder chunking handles the combined corpus, so answers reflect all uploaded documents.

### Legacy Document AI Flow

The original Document AI normalisation pipeline and Firestore schema are archived in `docs/history/OldApproach.md`. No new data is written to `docai/output/` under the managed RAG workflow.
