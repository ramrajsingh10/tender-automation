# Tender Automation Monorepo

This repository hosts the Tender Automation frontend plus the services that power the managed Vertex RAG pipeline. The web experience is a Next.js app deployed to Firebase Hosting, while Python FastAPI services (backend API, orchestrator, ingestion worker) are deployed to Google Cloud Run.

> **Vision snapshot:** The current implementation covers upload -> ingestion -> Vertex RAG playbook execution -> validation. Future phases (detailed in `docs/Knowledgedeck.md`) will add OCR enrichment, annexure generation, baseline project plans, task/RACI management, automated pre-flight checks, and Google Drive provisioning.

## Directory Layout
- `frontend/` - Next.js 15 application and supporting assets.
- `backend/` - FastAPI backend service.
- `services/` - FastAPI services deployed to Cloud Run (`orchestrator`, `ingest_worker`).
- `docs/` - Repository policies, architecture notes, and historical context.
- `.vscode/` - Command palette tasks for local workflows and Cloud Run deployments.

## Prerequisites
- Node.js 20+ and npm 10 with workspaces enabled.
- Python 3.11+ for FastAPI services (use a virtual environment locally).
- Firebase CLI and Google Cloud SDK authenticated against the `tender-automation-1008` project.

## Installation
```bash
npm install
```
This bootstraps workspace dependencies (currently the frontend package). Run the command from the repository root.

## Frontend
- Start dev server: `npm run frontend:dev`
- Lint: `npm run frontend:lint`
- Production build: `npm run frontend:build`
- Launch local production preview: `npm run frontend:start`

Environment variables for the web app live in `frontend/.env.example`. Copy that file to `frontend/.env.local` (or `frontend/.env.development.local`) and set `NEXT_PUBLIC_TENDER_BACKEND_URL` when targeting a non-production backend.

## Backend and Supporting Services
The FastAPI backend lives in `backend/`. Run it locally with:

```bash
uvicorn app.main:app --app-dir backend --reload
```

Key responsibilities:
- Tender processing: `POST /api/tenders/{tenderId}/process` imports the uploaded bundle into Vertex RAG, runs the managed playbook, and writes results JSON to Cloud Storage. Retrieve answers via `GET /api/tenders/{tenderId}/playbook`.
- Ad-hoc questions: `POST /api/rag/query` proxies a single prompt to the orchestrator, which calls Agent Builder + Gemini.
- RAG ingestion worker: `services/ingest_worker/` (Cloud Run) uses `VertexRagDataServiceClient.import_rag_files` to ingest documents once uploads finish.
- Orchestrator: `services/orchestrator/` (Cloud Run) reuses RagFile IDs, executes the playbook, and stores outputs in `parsedtenderdata`.

Deploy the backend, orchestrator, and ingest worker to Cloud Run with the VS Code tasks (`.vscode/tasks.json`) or manually via the documented `gcloud run deploy` commands.

## Testing
- Frontend lint/build checks: `npm run frontend:lint`, `npm run frontend:build`.
- Backend smoke tests (from a virtual environment):
  ```bash
  python -m pip install -r backend/requirements.txt pytest
  pytest backend
  ```
- Orchestrator and ingest worker tests follow the same pattern using their `requirements.txt`.
- VS Code tasks `python: test backend` and `python: test orchestrator` automate dependency installation plus pytest.

## Deployment Overview
- **Frontend**: `firebase deploy --only hosting:tender-app` runs `next build --no-lint`, exports static assets, and uploads to Firebase Hosting.
- **Services**: Use `.vscode/tasks.json` or direct CLI calls to deploy each Cloud Run service in `us-central1`.
- **Service accounts**: Follow [`docs/service-accounts.md`](docs/service-accounts.md) for IAM bindings.
- **Vertex AI (Agent Builder)**: Ensure service accounts have Vertex discovery/Agent Builder roles. Confirm `VERTEX_RAG_CORPUS_PATH`, `VERTEX_RAG_CORPUS_LOCATION`, and `VERTEX_RAG_GEMINI_MODEL` environment variables are set on orchestrator.
- **Backend <-> Orchestrator**: Configure `ORCHESTRATOR_BASE_URL` so the backend can forward `/api/rag/query` and playbook requests securely (Google-signed ID token).

## Additional Documentation
- [`docs/Knowledgedeck.md`](docs/Knowledgedeck.md) - comprehensive architecture, desired product flow, and roadmap (kept current).
- [`docs/NewApproach.md`](docs/NewApproach.md) - managed Vertex RAG architecture runbook.
- [`docs/task_list.md`](docs/task_list.md) - chronological work log plus outstanding tasks mapped to the long-term product vision.
- [`docs/service-accounts.md`](docs/service-accounts.md) - Cloud Run service account matrix.
- Legacy materials (DocAI flow, extractor architecture, historical Firestore schema) remain under `docs/history/` for reference.
