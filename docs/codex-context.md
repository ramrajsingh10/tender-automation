# Codex Engagement Protocol

## Purpose
- Partner with the user as an implementation-focused engineer while following the latest Codex CLI operating guidelines.
- Keep this document aligned with docs/codex-plan_mode.md and the expectations the user sets during a session.

## Repository Overview
- `frontend/` - Next.js 15 application deployed to Firebase Hosting.
- `backend/` - FastAPI service orchestrating tender uploads and Document AI parsing.
- `services/api-public` - FastAPI health endpoint published on Cloud Run.
- `services/api-private` - FastAPI service for authenticated integrations.
- `agents/` - Workspace for background automation (currently a placeholder).
- `docs/` - Collaboration guides, including this protocol and plan-mode guidance.

## Tech Stack & Tooling
- Frontend: Next.js 15, React 19, Tailwind CSS, TypeScript.
- Backend & services: Python 3.12, FastAPI, Google Cloud Storage, Document AI clients.
- Hosting: Firebase Hosting for the web app, Google Cloud Run for Python services.
- Tooling: npm workspaces (root scripts drive individual packages), VS Code tasks for gcloud deploys and pytest runs.

## Environment Layout
- Root `.env.example` captures shared deployment metadata and external endpoints.
- Frontend-specific variables live in `frontend/.env.example`; copy to `frontend/.env.local` for local work and keep real secrets out of git.
- Cloud Run services read configuration from environment variables (see `backend/cloudrun.env` for defaults).

## Key Commands
- Install dependencies: `npm install`
- Frontend scripts (run from repo root):
  - `npm run frontend:dev`
  - `npm run frontend:lint`
  - `npm run frontend:build`
  - `npm run frontend:start`
- Cloud Run deploy (see `.vscode/tasks.json` for canned commands):
  - Public: `gcloud run deploy api-public --source ./services/api-public --region us-central1 --allow-unauthenticated`
  - Private: `gcloud run deploy api-private --source ./services/api-private --region us-central1 --no-allow-unauthenticated`
- Python service smoke tests (virtual environment recommended):
  ```powershell
  python -m pip install -r services/api-public/requirements.txt pytest
  pytest services/api-public

  python -m pip install -r services/api-private/requirements.txt pytest
  pytest services/api-private
  ```

## Collaboration Workflow
- Use the planning tool for multi-step or non-trivial tasks; keep plans to at least two steps and update them as work progresses.
- It is acceptable to run non-destructive shell commands directly (for example `ls`, editors, tests) following the current sandbox rules; request approval if elevated permissions are needed.
- Summaries should reference the files examined (`path:line`) and call out risks, assumptions, or required follow-up.
- Respect existing repository changes; never revert or overwrite user work unless explicitly instructed.
- When ambiguity arises, pause and clarify with the user before proceeding.

## File Exploration & Communication
- Navigate the codebase proactively; no need for per-file approval, but keep the user informed about notable findings.
- Keep responses concise yet information-dense, mirroring the user's tone.
- Surface blockers immediately and propose options when trade-offs exist.

## Conflict Resolution
- If new directions conflict with this protocol or plan-mode guidance, ask the user to prioritize instructions.
- Default to conserving user intent and repository integrity when uncertain.
