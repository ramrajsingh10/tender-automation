# RAG Indexer Service

Transforms normalized tender documents into layout-aware chunks and upserts
them to Vertex AI Vector Search (Matching Engine).

## Responsibilities

- Chunk sections, tables, and fallback page blocks from the normalized document.
- Generate embeddings using Vertex AI text embedding models.
- Upsert datapoints into a Vector Search index endpoint.
- Persist chunk metadata to Firestore (`ragChunks` collection).

## Environment Variables

| Variable | Description |
| --- | --- |
| `GCP_PROJECT` | Google Cloud project ID |
| `VERTEX_LOCATION` | Vertex AI region (e.g. `us-central1`) |
| `VERTEX_INDEX_ENDPOINT_ID` | Vertex AI Index Endpoint resource ID (current: `6462051937788362752`) |
| `VERTEX_INDEX_ID` | Vertex AI Index resource ID (current: `3454808470983802880`) |
| `RAG_CHUNK_SIZE` | Optional max characters per chunk (default 1200) |
| `RAG_MAX_BATCH` | Optional batch size for upserts (default 50) |

Service account must have Firestore read/write and Vertex AI permissions.
See [`docs/service-accounts.md`](../../docs/service-accounts.md) for the exact
IAM bindings.

## Deployment

```bash
gcloud run deploy rag-indexer \
  --image gcr.io/$PROJECT_ID/rag-indexer \
  --region us-central1 \
  --service-account sa-rag@tender-automation-1008.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --set-env-vars "VERTEX_LOCATION=us-central1,VERTEX_INDEX_ID=3454808470983802880,VERTEX_INDEX_ENDPOINT_ID=6462051937788362752"
```

## Local Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload
```

Configure your gcloud credentials so Application Default Credentials can access
Vertex AI and Firestore.
