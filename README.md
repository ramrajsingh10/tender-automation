# Tender Automation Monorepo

This repository hosts the Tender Automation frontend, backend services, and automation agents in a single monorepo. The web experience is a Next.js app deployed to Firebase Hosting, while Python FastAPI services are deployed to Google Cloud Run. Additional automation will live under the agents/ hierarchy.

## Directory Layout
- frontend  Next.js 15 application and supporting assets.
- services/  FastAPI services deployed to Cloud Run (ingest_api, orchestrator, artifact-builder (legacy), qa_loop (placeholder), rag-trigger-poc).
- agents/  Placeholder for background agents (e.g., agents/ingestion).
- docs/  Repository policies and operating procedures (codex-context.md, codex-plan_mode.md).
- .vscode/  Task definitions for local workflows, Cloud Run deployments, and Python testing.

## Prerequisites
- Node.js 20+ and npm 10 with workspaces enabled.
- Python 3.11+ for FastAPI services (recommend using a virtual environment).
- Firebase CLI and Google Cloud SDK authenticated against the tender-automation-1008 project.

## Installation
```bash
npm install
```
This bootstraps workspace dependencies (currently the frontend package).

## Frontend
- Start dev server: `npm run frontend:dev`
  - Lint: `npm run frontend:lint`
  - Production build: `npm run frontend:build`
  - Start production server locally: `npm run frontend:start`
- For local backend testing, create `frontend/.env.development.local` with overrides (e.g. `NEXT_PUBLIC_TENDER_BACKEND_URL=http://localhost:8000`). The checked-in `.env.local` is used for deployments and points at the production API.

Environment variables for the web app live in frontend/.env.example; copy to frontend/.env.local for local development.

## Backend Services
Each FastAPI service includes a `main.py` and `requirements.txt`. Run any service locally with:

```bash
uvicorn main:app --app-dir services/<service-name> --reload
```

Deploy the services to Cloud Run with the provided VS Code tasks or by running the `gcloud run deploy` commands defined in `.vscode/tasks.json`.

- Tender processing: `POST /api/tenders/{tenderId}/process` imports the uploaded bundle into Vertex RAG, runs the managed playbook, and writes the results JSON to Cloud Storage. Retrieve the latest answers via `GET /api/tenders/{tenderId}/playbook`.
- Ad-hoc questions: `POST /api/rag/query` proxies a single prompt to Agent Builder for exploration or validation.

## Testing
- Web lint/build checks: `npm run frontend:lint` and `npm run frontend:build`.
- Python service smoke tests (from a virtual environment):
  ```bash
  python -m pip install -r services/<service-name>/requirements.txt pytest
  pytest services/<service-name>
  ```
- VS Code tasks execute the same installation + pytest flow for individual services.

## Agents
agents/ contains scaffolding for future worker-style automation. Add one subdirectory per agent, document runtime requirements, and supply env templates (.env.example) alongside the code.

## Managed RAG Roadmap
We now rely on Vertex AI Agent Builder for document ingestion and retrieval.  
High-level plans, phased rollout, and open questions live in [`docs/NewApproach.md`](docs/NewApproach.md).

## Deployment
- **Frontend**: firebase.json points Hosting to frontend and deploys the framework build artifact in frontend/.next. Run `npm run frontend:build` before firebase deploy --only hosting.
- **GitLab CI**: ensure the build job exports `NEXT_PUBLIC_TENDER_BACKEND_URL=https://tender-backend-981270825391.us-central1.run.app` (for example by setting a protected CI/CD variable) so production bundles never fall back to `http://localhost:8000`.
- **Services**: Use the gcloud tasks in .vscode/tasks.json or replicate the commands in CI/CD to deploy each FastAPI service to Cloud Run (us-central1).
- **Service accounts**: Follow [`docs/service-accounts.md`](docs/service-accounts.md) when assigning IAM and attaching service accounts to Cloud Run services.
- **Google Drive**: Set `GOOGLE_DRIVE_PARENT_FOLDER_ID=0AIIJEYSn69gTUk9PVA` (Tenders shared drive) for the artifact builder service; Secret Manager usage is outlined in `services/artifact-builder/README.md`.
- **Vertex AI (Agent Builder)**: Ensure service accounts have `discoveryengine.admin` and `discoveryengine.user` roles for document ingestion and query access. Enable `discoveryengine.googleapis.com`, capture the data store ID for `VERTEX_RAG_DATA_STORE_ID`, and watch the `text-multilingual-embedding-002` quota (`online_prediction_requests_per_base_model`).
- **Backend ↔ Orchestrator**: Set `ORCHESTRATOR_BASE_URL` so the tender backend can forward `/api/rag/query` requests to the orchestrator proxy.

## Additional Documentation
- docs/codex-context.md outlines collaboration and workflow expectations.
- docs/codex-plan_mode.md captures the Plan Mode operating instructions for Codex.
- docs/NewApproach.md documents the managed Vertex RAG pipeline.
- docs/OldApproach.md archives the legacy DocAI + custom RAG workflow and issues we
  encountered along the way.
