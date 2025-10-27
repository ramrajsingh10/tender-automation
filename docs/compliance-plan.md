# Compliance Checklist and Baseline Plan Generators

Future pipeline stages will transform approved facts into compliance deliverables and an initial project plan. This document captures the target behaviour and open items before implementation.

## Inputs

- Approved facts (`facts` collection) with `status = approved` representing deadlines, requirements, penalties, and other key metadata.
- Annexure artefacts (Google Docs links) for reference.
- Optional user-provided templates (Google Docs for checklist, JSON/YAML for baseline plan structure).

## Outputs

- Compliance checklist (for example Google Doc or Google Sheet) listing each requirement with approval status, responsible party, due dates, and links back to provenance.
- Baseline project plan (for example Google Sheet or exported JSON) containing deadline-driven, requirement-driven, and compliance tasks ready for import into PM tooling.
- Firestore entries in `artifacts/{id}` referencing generated documents and the source fact versions.

## Proposed Architecture

1. **Data Aggregation Service** - collects approved facts grouped by category (deadlines, requirements, penalties) and normalises them into structured DTOs.
2. **Checklist Generator** - merges the data into a template (Google Docs/Sheets) using the Drive API, including status columns for BA sign-off.
3. **Plan Generator** - maps deadlines/requirements into tasks (start/end dates, predecessors, owners). Uses simple heuristics initially, later replaced with a rule engine or LLM prompting.
4. **Artifact Recorder** - stores resulting document IDs/links alongside source version metadata in Firestore.

## Orchestrator Integration

- New tasks: `artifact.checklist`, `artifact.plan`. They depend on required facts being approved; orchestrator should skip if prerequisites are missing.
- Services can reuse the annexure/artifact builder pattern (FastAPI + Google Docs API).

## Outstanding Work

- Enhance automated requirement extraction (Gemini/Agent Builder) to classify requirements (technical vs financial), capture owners, and produce confidence levels.
- Define checklist/plan templates (doc IDs) and make them configurable via environment variables.
- Implement the generators and hook them into the artifact pipeline once upstream data is reliable.
