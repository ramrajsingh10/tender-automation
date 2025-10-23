## Tender Automation Backend (Managed RAG Pipeline)

Python FastAPI service that powers the tender upload pipeline. It now
coordinates multi-file uploads, invokes the orchestrator’s Vertex RAG
playbook, and exposes APIs for reviewing answers.

Key capabilities:

- Create tender sessions and return signed upload URLs.
- Record upload completion status for every file in a bundle.
- Trigger the orchestrator to import the bundle into Vertex RAG, run the
  managed question set, and write the JSON results to Cloud Storage.
- Expose `/api/tenders/{tenderId}/playbook` so the UI (and operators) can
  inspect the latest AI answers with citations.

---

### 1. Prerequisites

1. **Python 3.11+** installed locally.
2. **Google Cloud credentials** on the machine running the service:
   - Activate Application Default Credentials with `gcloud auth application-default login`, *or*
   - Point `GOOGLE_APPLICATION_CREDENTIALS` to a service account key that has `roles/storage.objectAdmin`.
3. Cloud resources already provisioned:
   - Buckets: `rawtenderdata`, `parsedtenderdata`.
   - Vertex Agent Builder data store + rag corpus (see `docs/NewApproach.md`).
   - Orchestrator Cloud Run service reachable via `ORCHESTRATOR_BASE_URL`.
4. Dedicated service account configured as described in [`docs/service-accounts.md`](../docs/service-accounts.md).

### 2. Environment variables

Set these before starting the server (values shown are defaults used if nothing is provided):

| Variable | Description | Default |
| --- | --- | --- |
| `GCP_PROJECT_ID` | Google Cloud project hosting the resources | _(empty)_ |
| `RAW_TENDER_BUCKET` | Bucket for original uploads | `rawtenderdata` |
| `PARSED_TENDER_BUCKET` | Bucket for playbook outputs | `parsedtenderdata` |
| `SIGNED_URL_EXPIRATION_SECONDS` | Validity period for upload URLs | `900` (15 min) |
| `API_ALLOWED_ORIGINS` | Comma separated list of CORS origins | `*` |
| `STORE_BACKEND` | `firestore` (default) or `memory` | `memory` |
| `FIRESTORE_COLLECTION` | Firestore collection that stores tender sessions | `tenderSessions` |
| `ORCHESTRATOR_BASE_URL` | Base URL for the Cloud Run orchestrator | _(empty)_ |
| `RAG_CLIENT_TIMEOUT_SECONDS` | Timeout (seconds) when calling the orchestrator | `30` |

Example (PowerShell):

```powershell
$env:GCP_PROJECT_ID = "tender-automation-1008"
$env:RAW_TENDER_BUCKET = "rawtenderdata"
$env:PARSED_TENDER_BUCKET = "parsedtenderdata"
$env:ORCHESTRATOR_BASE_URL = "https://orchestrator-lblqj4e2ba-uc.a.run.app"
$env:API_ALLOWED_ORIGINS = "http://localhost:3000"
$env:STORE_BACKEND = "firestore"
$env:FIRESTORE_COLLECTION = "tenderSessions"
```

### 3. Install dependencies

From the repository root (or inside `/backend`), run:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

### 4. Run the API

```powershell
uvicorn app.main:app --reload --port 8000 --app-dir backend
```

The service exposes OpenAPI docs at `http://localhost:8000/docs`.

### 5. API overview

| Endpoint | Method | Description |
| --- | --- | --- |
| `/health` | GET | Simple health probe |
| `/api/tenders` | POST | Create a tender session (returns `tenderId` and upload limits) |
| `/api/tenders/{tenderId}` | GET | Inspect session status and file list |
| `/api/tenders/{tenderId}/uploads/init` | POST | Request a signed URL for one file |
| `/api/tenders/{tenderId}/uploads/{fileId}/complete` | POST | Mark upload success/failure |
| `/api/tenders/{tenderId}/process` | POST | Trigger the orchestrator playbook (imports into Vertex RAG, runs questions, writes JSON) |
| `/api/tenders/{tenderId}/playbook` | GET | Fetch the most recent playbook results from Cloud Storage |
| `/api/rag/query` | POST | Proxy a single ad-hoc question to Agent Builder |

### 6. Manual test script (Postman / curl)

1. **Create session**

   ```powershell
   Invoke-RestMethod -Method POST -Uri http://localhost:8000/api/tenders -Body '{}' -ContentType 'application/json'
   ```

2. **Initialise upload**

   ```powershell
   $body = @{
     filename = "tender.pdf"
     sizeBytes = 123456
     contentType = "application/pdf"
   } | ConvertTo-Json

   Invoke-RestMethod -Method POST -Uri "http://localhost:8000/api/tenders/$tenderId/uploads/init" `
     -Body $body -ContentType 'application/json'
   ```

   Use the returned `uploadUrl` with `Invoke-WebRequest -Method Put` (or curl) to push the file.

3. **Mark complete**

   ```powershell
   Invoke-RestMethod -Method POST -Uri "http://localhost:8000/api/tenders/$tenderId/uploads/$fileId/complete" `
     -Body '{ "status": "uploaded" }' -ContentType 'application/json'
   ```

4. **Check session**

   ```powershell
   Invoke-RestMethod -Uri "http://localhost:8000/api/tenders/$tenderId"
   ```

5. **Trigger the playbook (after all files uploaded)**

   ```powershell
   Invoke-RestMethod -Method POST -Uri "http://localhost:8000/api/tenders/$tenderId/process"
   ```

   The response immediately reflects the updated status (`parsing`). When the orchestrator completes, the session transitions to `parsed` and `parse.outputUri` points to the JSON file written under `gs://parsedtenderdata/{tenderId}/rag/`.

6. **Inspect AI answers**

   ```powershell
   Invoke-RestMethod -Uri "http://localhost:8000/api/tenders/$tenderId/playbook"
   ```

   The payload matches the structure documented in `docs/storage-and-events.md`.

### 7. Next steps

- Harden auth (JWT / Firebase Auth) and observability (structured logging).
- Extend the playbook output writer if you want to persist summaries to Firestore or other data stores.

---

### Appendix: Container build (Cloud Run)

A `Dockerfile` is included so you can deploy the service to Cloud Run.

Build and push:

```powershell
gcloud builds submit --tag gcr.io/$env:GCP_PROJECT_ID/tender-backend .
```

Run locally for testing:

```powershell
docker build -f backend/Dockerfile -t tender-backend .
docker run --rm -p 8080:8080 `
  -e GCP_PROJECT_ID=$env:GCP_PROJECT_ID `
  -e RAW_TENDER_BUCKET=$env:RAW_TENDER_BUCKET `
  -e PARSED_TENDER_BUCKET=$env:PARSED_TENDER_BUCKET `
  -e ORCHESTRATOR_BASE_URL=$env:ORCHESTRATOR_BASE_URL `
  tender-backend
```

Deploy to Cloud Run (ensure `sa-backend@tender-automation-1008.iam.gserviceaccount.com`
exists as documented in `docs/service-accounts.md`):

```powershell
gcloud run deploy tender-backend `
  --image gcr.io/$env:GCP_PROJECT_ID/tender-backend `
  --platform managed `
  --region us-central1 `
  --allow-unauthenticated `
  --service-account sa-backend@tender-automation-1008.iam.gserviceaccount.com `
  --set-env-vars GCP_PROJECT_ID=$env:GCP_PROJECT_ID,RAW_TENDER_BUCKET=$env:RAW_TENDER_BUCKET,PARSED_TENDER_BUCKET=$env:PARSED_TENDER_BUCKET,ORCHESTRATOR_BASE_URL=$env:ORCHESTRATOR_BASE_URL,SIGNED_URL_EXPIRATION_SECONDS=900,API_ALLOWED_ORIGINS=https://tender-automation--tender-automation-1008.us-central1.hosted.app
```

Attach the service account that has Storage and Discovery Engine roles if needed:

```powershell
gcloud run services update tender-backend `
  --platform managed `
  --region us-central1 `
  --service-account sa-backend@tender-automation-1008.iam.gserviceaccount.com
```
