# Cloud Run Service Accounts

This document captures the mapping between each Tender Automation Cloud Run service and the dedicated service account it runs under. Use it as the source of truth when deploying, rotating credentials, or auditing IAM bindings.

All service accounts live in the `tender-automation-1008` project and follow the `sa-<workload>@tender-automation-1008.iam.gserviceaccount.com` naming convention.

## Service -> Account Matrix

| Cloud Run Service | Service Account | Primary IAM Roles (project scope unless noted) | Notes |
| --- | --- | --- | --- |
| `tender-backend` | `sa-backend@tender-automation-1008.iam.gserviceaccount.com` | `roles/datastore.user`, `roles/storage.objectAdmin`, `roles/discoveryengine.user` | Public API surface. Manages uploads, triggers ingestion, and proxies `/api/rag/query`. |
| `ingest-worker` | `sa-ingest@tender-automation-1008.iam.gserviceaccount.com` | `roles/datastore.user`, `roles/storage.objectViewer`, `roles/pubsub.publisher`, `roles/discoveryengine.admin` | Imports bundles into Vertex RAG and records RagFile metadata. Grant bucket-level viewer access to `rawtenderdata` and `parsedtenderdata`. |
| `orchestrator` | `sa-orchestrator@tender-automation-1008.iam.gserviceaccount.com` | `roles/datastore.user`, `roles/discoveryengine.user`, `roles/aiplatform.user`, `roles/storage.objectAdmin` (bucket scoped) | Runs Gemini playbooks, powers `/rag/query`, and writes outputs to Cloud Storage. |
| `tender-automation` (Firebase Hosting) | Managed by Firebase | `service-981270825391@gcp-sa-firebaseapphosting.iam.gserviceaccount.com` | Auto-provisioned hosting service account for the Next.js frontend. |
| _Future: annexure-generator_ | `sa-annexure@tender-automation-1008.iam.gserviceaccount.com` | (planned) Drive API writer, Document AI processor, Storage viewer | Placeholder for automated annexure/template generation service. |
| _Future: plan-orchestrator_ | `sa-plan@tender-automation-1008.iam.gserviceaccount.com` | (planned) Firestore editor, Pub/Sub publisher, Notifications API | Placeholder for baseline project plan and RACI automation. |

Legacy extractor, artifact-builder, RAG indexer, and QA loop services have been retired. Their service accounts remain in IAM but can be disabled once we confirm no workloads depend on them.

Future Cloud Run workloads (for example baseline plan generator, submission checker) should follow the same pattern: create a dedicated `sa-<workload>` account, grant only the roles required, and document the mapping here.

## Create or Update the Service Accounts

```bash
PROJECT_ID=tender-automation-1008

# Create accounts (no effect if they already exist)
for SA in backend ingest orchestrator; do
  gcloud iam service-accounts create "sa-${SA}" \
    --display-name "Tender ${SA//-/ } service account" \
    --project "${PROJECT_ID}"
done
```

Assign project-level roles (`gcloud projects add-iam-policy-binding`) and any resource-scoped roles (for example Cloud Storage or Pub/Sub). Example bindings:

```bash
# Firestore access
for SA in backend ingest orchestrator; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:sa-${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/datastore.user"
done

# Storage access
for SA in backend; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:sa-${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/storage.objectAdmin"
done

for SA in ingest; do
  for BUCKET in rawtenderdata parsedtenderdata; do
    gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
      --member="serviceAccount:sa-${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
      --role="roles/storage.objectViewer"
  done
done

# Pub/Sub publish
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:sa-ingest@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"

# Vertex AI access
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:sa-ingest@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/discoveryengine.admin"

for SA in backend orchestrator; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:sa-${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/discoveryengine.user"
done

# Capture the deployed Vertex AI resources so services can reference them.
# Current managed RAG corpus:
#   VERTEX_RAG_CORPUS_PATH=projects/tender-automation-1008/locations/us-east4/ragCorpora/6917529027641081856
#   VERTEX_RAG_EMBEDDING_MODEL=text-multilingual-embedding-002
# Store them in Secret Manager or environment templates as appropriate.
```

Legacy extractor, artifact builder, and QA loop accounts can be removed once no workloads depend on them.

## Attach the Accounts to Cloud Run Services

After updating IAM, redeploy or patch each Cloud Run service so it uses the matching account:

```bash
REGION=us-central1

declare -A SERVICES=(
  [tender-backend]=sa-backend
  [ingest-worker]=sa-ingest
  [orchestrator]=sa-orchestrator
)

for SERVICE in "${!SERVICES[@]}"; do
  gcloud run services update "${SERVICE}" \
    --service-account="${SERVICES[$SERVICE]}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --region="${REGION}" \
    --project="${PROJECT_ID}"
done
```

Confirm the attachment:

```bash
gcloud run services describe ingest-worker \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --format="value(spec.template.spec.serviceAccountName)"
```

## Retire the Legacy Editor Account

Once every service runs with its dedicated account, strip `roles/editor` from the default Compute Engine service account:

```bash
gcloud projects remove-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:981270825391-compute@developer.gserviceaccount.com" \
  --role="roles/editor"
```

Audit the remaining permissions periodically:

```bash
gcloud projects get-iam-policy "${PROJECT_ID}" \
  --flatten="bindings[]" \
  --filter="bindings.members:981270825391-compute@developer.gserviceaccount.com"
```

Log the command output in change-management tickets or deployment notes so the access shift is recorded for compliance.
