# Tender Automation Monorepo

This repository hosts the Tender Automation frontend, backend services, and automation agents in a single monorepo. The web experience is a Next.js app deployed to Firebase Hosting, while Python FastAPI services are deployed to Google Cloud Run. Additional automation will live under the gents/ hierarchy.

## Directory Layout
- pps/web – Next.js 15 application and supporting assets.
- services/api-public – Public FastAPI service exposing /healthz for Cloud Run.
- services/api-private – Private FastAPI service with authenticated /ping endpoint.
- gents/ – Placeholder for background agents (e.g., gents/ingestion).
- docs/ – Repository policies and operating procedures (codex-context.md, codex-plan_mode.md).
- .vscode/ – Task definitions for local workflows, Cloud Run deployments, and Python testing.

## Prerequisites
- Node.js 20+ and npm 10 with workspaces enabled.
- Python 3.11+ for FastAPI services (recommend using a virtual environment).
- Firebase CLI and Google Cloud SDK authenticated against the 	ender-automation-1008 project.

## Installation
`ash
npm install
`
This bootstraps workspace dependencies (currently the pps/web package).

## Frontend (apps/web)
- Start dev server: 
pm run web:dev
- Lint: 
pm run web:lint
- Production build: 
pm run web:build
- Start production server locally: 
pm run web:start

Environment variables for the web app live in pps/web/.env.example; copy to pps/web/.env.local for local development.

## Backend Services
Each FastAPI service includes a main.py and equirements.txt.

`ash
# api-public
uvicorn main:app --app-dir services/api-public --reload

# api-private
uvicorn main:app --app-dir services/api-private --reload
`

Deploy the services to Cloud Run with the provided VS Code tasks or by running the same gcloud run deploy commands defined in .vscode/tasks.json.

## Testing
- Web lint/build checks: 
pm run web:lint and 
pm run web:build.
- Python service smoke tests (from a virtual environment):
  `ash
  python -m pip install -r services/api-public/requirements.txt pytest
  pytest services/api-public

  python -m pip install -r services/api-private/requirements.txt pytest
  pytest services/api-private
  `
- VS Code tasks python: test api-public / python: test api-private perform the same installation + pytest flow.

## CI/CD Notes
- Ensure pipelines run 
pm run web:build from the repo root and store artifacts from pps/web/.next if needed.
- When adding Python service tests to CI, replicate the commands above before executing pytest.

## Agents
gents/ contains scaffolding for future worker-style automation. Add one subdirectory per agent, document runtime requirements, and supply env templates (.env.example) alongside the code.

## Deployment
- **Frontend**: irebase.json points Hosting to pps/web and deploys the framework build artifact in pps/web/.next. Run 
pm run web:build before irebase deploy --only hosting.
- **Services**: Use the gcloud tasks in .vscode/tasks.json or replicate the commands in CI/CD to deploy each FastAPI service to Cloud Run (us-central1).

## Additional Documentation
- docs/codex-context.md outlines collaboration and workflow expectations.
- docs/codex-plan_mode.md captures the Plan Mode operating instructions for Codex.