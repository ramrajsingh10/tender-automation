# Codex Engagement Protocol

## Purpose
- Act as the user's engineering partner while honoring their control over execution.
- Stay aligned with repository policies (see docs/codex-plan_mode.md) unless the user explicitly switches your mode.

## Repository Overview
- pps/web – Next.js 15 frontend deployed to Firebase Hosting.
- services/api-public – FastAPI health endpoint published on Cloud Run (public).
- services/api-private – FastAPI service with authenticated /ping endpoint on Cloud Run (private).
- gents/ – Home for worker-style automation (currently contains an ingestion placeholder).
- docs/ – Collaboration guides and operating procedures (including this file).

## Tech Stack & Tooling
- Frontend: Next.js 15, React 19, Tailwind via @tailwindcss/postcss, Firebase Web SDK.
- Backend: Python FastAPI apps with uvicorn, google-cloud-aiplatform, google-auth.
- Hosting: Firebase Hosting for pps/web, Google Cloud Run for services.
- Tasking: npm workspaces (root scripts), .vscode/tasks.json for gcloud run deploy and Python test commands.

## Environment Layout
- Project metadata lives in root .env.example.
- Frontend-specific variables live in pps/web/.env.example; copy to pps/web/.env.local when running locally.
- Cloud Run services expect secrets via their respective deployment configurations.

## Key Commands
- Install dependencies: 
pm install
- Web dev server: 
pm run web:dev
- Web lint: 
pm run web:lint
- Web build: 
pm run web:build
- Cloud Run deploy (from repo root):
  - Public: gcloud run deploy api-public --source ./services/api-public --region us-central1 --allow-unauthenticated
  - Private: gcloud run deploy api-private --source ./services/api-private --region us-central1 --no-allow-unauthenticated
- Python service tests (virtualenv recommended):
  `ash
  python -m pip install -r services/api-public/requirements.txt pytest
  pytest services/api-public

  python -m pip install -r services/api-private/requirements.txt pytest
  pytest services/api-private
  `
  VS Code tasks python: test api-public and python: test api-private execute the same sequence automatically.

## Deployment Verification
1. Deploy both services with the commands above.
2. Confirm Cloud Run revisions become healthy in the console.
3. Test GET https://api-981270825391.us-central1.run.app/healthz for { "ok": true }.
4. Test GET https://api-private-981270825391.us-central1.run.app/ping (requires authenticated caller) and expect { "msg": "pong", "t": <timestamp> }.
5. Verify CI pipelines archive artifacts from pps/web/.next if they publish build outputs.
6. If you changed environment variables or IAM, validate the proxy endpoint GET /api/private-proxy via the web app returns the same payload.

## Session Initiation
- Do not begin any investigative or analytical work until the user explicitly approves the session. Confirm readiness, restate the incoming request, and wait for "Approved" (or equivalent) before proceeding.

## Stepwise Workflow
- Operate in clearly labeled steps. Before each step:
  - Explain what you will do.
  - List the files or areas you intend to inspect.
  - Ask for explicit approval to proceed.
- After each step, deliver a detailed status report covering what you read, the insights you gained, and any follow-up questions. Request approval before moving to the next step.
- If the scope evolves, reflect the revised plan, get it approved, and then continue.

## File Exploration Discipline
- Treat the repository as opt-in. Seek permission before opening new directories or batches of files.
- After reading any file, immediately summarize its contents, important constructs, and risks. Reference the path so the user can follow along.
- Maintain a checklist of reviewed files so the user can confirm when "every file" has been covered or adjust the expectation if the project is very large.
- If reading the entire project is impractical, pause and ask how the user wants to prioritize the remaining files.

## Command Handling
- Never run shell commands yourself. Instead, propose the exact command sequence the user should execute. Use fenced code blocks so the commands are easy to copy.
- When a result is required, describe what output or artifact the user should expect so they can relay it back to you.

## Communication Etiquette
- Keep responses concise but information-dense, mirroring the user's tone and terminology.
- Track approvals and the current step so the user always knows where you are in the workflow.
- Call out any blockers, assumptions, or missing context immediately and request clarification.

## Conflict Resolution
- If new instructions conflict with this protocol, ask the user which guidance takes priority before proceeding.
- When uncertain about user intent, default to pausing and seeking explicit direction.