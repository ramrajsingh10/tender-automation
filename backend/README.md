## Tender Automation Backend (Phase 1 MVP)

Python FastAPI service that powers the tender upload pipeline. It exposes APIs for:

- Creating tender sessions (one per upload batch).
- Requesting signed upload URLs for raw documents.
- Recording upload completion status to drive downstream parsing.

> **Note:** By default the service uses Firestore to persist tender sessions in production. Set `STORE_BACKEND=memory` if you need
> an in-memory store for quick local experiments.

---

### 1. Prerequisites

1. **Python 3.11+** installed locally.
2. **Google Cloud credentials** on the machine running the service:
   - Activate Application Default Credentials with `gcloud auth application-default login`, *or*
   - Point `GOOGLE_APPLICATION_CREDENTIALS` to a service account key file that has `roles/storage.objectAdmin`.
3. Cloud resources already provisioned:
   - Buckets: `rawtenderdata`, `parsedtenderdata`.
   - Document AI processor(s) (used later in Phase 2).
4. Dedicated service account configured as described in [`docs/service-accounts.md`](../docs/service-accounts.md).

### 2. Environment variables

Set these before starting the server (values shown are defaults used if nothing is provided):

| Variable | Description | Default |
| --- | --- | --- |
| `GCP_PROJECT_ID` | Google Cloud project hosting the resources | _(empty)_ |
| `RAW_TENDER_BUCKET` | Bucket for original uploads | `rawtenderdata` |
| `PARSED_TENDER_BUCKET` | Bucket for parser outputs | `parsedtenderdata` |
| `DOCUMENT_AI_LOCATION` | Region for Document AI processors | `us` |
| `DOCUMENT_AI_PROCESSOR_ID` | Processor used in Phase 2 | _(empty)_ |
| `SIGNED_URL_EXPIRATION_SECONDS` | Validity period for upload URLs | `900` (15 min) |
| `API_ALLOWED_ORIGINS` | Comma separated list of CORS origins | `*` |
| `STORE_BACKEND` | `firestore` (default) or `memory` | `memory` |
| `FIRESTORE_COLLECTION` | Firestore collection that stores tender sessions | `tenderSessions` |

Example (PowerShell):

```powershell
$env:GCP_PROJECT_ID = "tender-automation-1008"
$env:RAW_TENDER_BUCKET = "rawtenderdata"
$env:PARSED_TENDER_BUCKET = "parsedtenderdata"
$env:DOCUMENT_AI_LOCATION = "us"
$env:DOCUMENT_AI_PROCESSOR_ID = "your-processor-id"
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
| `/api/tenders/{tenderId}/process` | POST | Trigger Document AI parsing (runs in background) |

Payload examples are available via the Swagger UI.

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

5. **Trigger parsing (after all files uploaded)**

   ```powershell
   Invoke-RestMethod -Method POST -Uri "http://localhost:8000/api/tenders/$tenderId/process"
   ```

   Poll the status endpoint until `status` becomes `parsed` or `failed`. Parsed sessions include `parse.outputUri` with the `gs://` destination produced by Document AI.

### 7. Next steps

- Wire the Document AI trigger (Part 2) to call the processor once status hits `UPLOADED`.
- Harden auth (JWT / Firebase Auth) and observability (structured logging).

---

### Appendix: Container build (Cloud Run)

A `Dockerfile` is included so you can deploy the service to Cloud Run.

Build and push:

```powershell
gcloud builds submit --config cloudbuild.yaml  # if you add one
# or directly
gcloud builds submit --tag gcr.io/$env:GCP_PROJECT_ID/tender-backend .
```

Run locally for testing:

```powershell
docker build -f backend/Dockerfile -t tender-backend .
docker run --rm -p 8080:8080 `
  -e GCP_PROJECT_ID=$env:GCP_PROJECT_ID `
  -e RAW_TENDER_BUCKET=$env:RAW_TENDER_BUCKET `
  -e PARSED_TENDER_BUCKET=$env:PARSED_TENDER_BUCKET `
  -e DOCUMENT_AI_LOCATION=$env:DOCUMENT_AI_LOCATION `
  -e DOCUMENT_AI_PROCESSOR_ID=$env:DOCUMENT_AI_PROCESSOR_ID `
  tender-backend
```

Deploy to Cloud Run (ensure `sa-backend@tender-automation-1008.iam.gserviceaccount.com`
exists as documented in `docs/service-accounts.md`):

```powershell
gcloud run deploy tender-backend `
  --image gcr.io/$env:GCP_PROJECT_ID/tender-backend `
  --platform managed `
  --region $env:DOCUMENT_AI_LOCATION `
  --allow-unauthenticated `
  --service-account sa-backend@tender-automation-1008.iam.gserviceaccount.com `
  --set-env-vars GCP_PROJECT_ID=$env:GCP_PROJECT_ID,RAW_TENDER_BUCKET=$env:RAW_TENDER_BUCKET,PARSED_TENDER_BUCKET=$env:PARSED_TENDER_BUCKET,DOCUMENT_AI_LOCATION=$env:DOCUMENT_AI_LOCATION,DOCUMENT_AI_PROCESSOR_ID=$env:DOCUMENT_AI_PROCESSOR_ID,SIGNED_URL_EXPIRATION_SECONDS=900,API_ALLOWED_ORIGINS=https://tender-automation--tender-automation-1008.us-central1.hosted.app
```

Attach the service account that has Storage + Document AI roles if needed:

```powershell
gcloud run services update tender-backend `
  --platform managed `
  --region $env:DOCUMENT_AI_LOCATION `
  --service-account sa-backend@tender-automation-1008.iam.gserviceaccount.com
```
