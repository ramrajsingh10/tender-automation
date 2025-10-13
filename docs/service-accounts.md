# Cloud Run Service Accounts

This document captures the mapping between each Tender Automation Cloud Run
service and the dedicated service account it runs under. Use it as the source
of truth when deploying, rotating credentials, or auditing IAM bindings.

All service accounts live in the `tender-automation-1008` project and follow
the `sa-<workload>@tender-automation-1008.iam.gserviceaccount.com` naming
convention.

## Service → Account Matrix

| Cloud Run Service | Service Account | Primary IAM Roles (project scope unless noted) | Notes |
| --- | --- | --- | --- |
| `tender-backend` | `sa-backend@tender-automation-1008.iam.gserviceaccount.com` | `roles/datastore.user`, `roles/storage.objectAdmin`, `roles/documentai.apiUser` | Launches Document AI batch jobs and updates tender metadata. |
| `ingest-api` | `sa-ingest@tender-automation-1008.iam.gserviceaccount.com` | `roles/datastore.user`, `roles/storage.objectViewer`, `roles/pubsub.publisher` | Consumes Document AI outputs, publishes pipeline triggers. Grant bucket-level `roles/storage.objectViewer` on `rawtenderdata` and `parsedtenderdata`. |
| `pipeline-orchestrator` | `sa-orchestrator@tender-automation-1008.iam.gserviceaccount.com` | `roles/datastore.user` | Persists pipeline runs and calls downstream services via HTTPS. Attach additional `roles/run.invoker` grants to target services when enforcing IAM-based invocation. |
| `extractor-deadlines` | `sa-extractor-deadlines@tender-automation-1008.iam.gserviceaccount.com` | `roles/datastore.user` | Writes deadline facts to Firestore. |
| `extractor-emd` | `sa-extractor-emd@tender-automation-1008.iam.gserviceaccount.com` | `roles/datastore.user` | Writes earnest-money facts to Firestore. |
| `extractor-requirements` | `sa-extractor-requirements@tender-automation-1008.iam.gserviceaccount.com` | `roles/datastore.user` | Writes requirements facts to Firestore. |
| `extractor-penalties` | `sa-extractor-penalties@tender-automation-1008.iam.gserviceaccount.com` | `roles/datastore.user` | Writes penalties facts to Firestore. |
| `extractor-annexures` | `sa-extractor-annexures@tender-automation-1008.iam.gserviceaccount.com` | `roles/datastore.user` | Locates annexure references and stores them in Firestore. |
| `artifact-annexures` | `sa-artifact@tender-automation-1008.iam.gserviceaccount.com` | `roles/datastore.user`, `roles/storage.objectViewer`, `roles/drive.file` | Reads annexure payloads, fetches PDFs from Cloud Storage, and uploads Google Docs into the shared Drive folder. |
| `rag-indexer` | `sa-rag@tender-automation-1008.iam.gserviceaccount.com` | `roles/datastore.user`, `roles/aiplatform.user`, `roles/aiplatform.indexAdmin` | Chunks documents, writes embeddings to Vertex AI Vector Search, and persists chunk metadata. |
| `qa-loop` | `sa-qa-loop@tender-automation-1008.iam.gserviceaccount.com` | `roles/datastore.user` | Records QA acknowledgements and routing decisions. |

Future Cloud Run workloads (for example checklist or baseline-plan generators)
should follow the same pattern: create a dedicated `sa-<workload>` account,
grant only the roles required, and document the mapping here.

## Create or Update the Service Accounts

```bash
PROJECT_ID=tender-automation-1008

# Create accounts (no effect if they already exist)
for SA in backend ingest orchestrator extractor-deadlines extractor-emd \
          extractor-requirements extractor-penalties extractor-annexures \
          artifact rag qa-loop; do
  gcloud iam service-accounts create "sa-${SA}" \
    --display-name "Tender ${SA//-/ } service account" \
    --project "${PROJECT_ID}"
done
```

Assign project-level roles (`gcloud projects add-iam-policy-binding`) and any
resource-scoped roles (for example Cloud Storage or Pub/Sub). Example bindings:

```bash
# Firestore access
for SA in backend ingest orchestrator extractor-deadlines extractor-emd \
          extractor-requirements extractor-penalties extractor-annexures \
          artifact rag qa-loop; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:sa-${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/datastore.user"
done

# Storage access
for SA in backend artifact; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:sa-${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/storage.objectAdmin"
done

for SA in ingest artifact; do
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

# Document AI invocation
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:sa-backend@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/documentai.apiUser"

# Vertex AI access
for ROLE in roles/aiplatform.user roles/aiplatform.indexAdmin; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:sa-rag@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="${ROLE}"
done

# Capture the deployed Vertex AI resources so services can reference them.
# Current production values:
#   VERTEX_LOCATION=us-central1
#   VERTEX_INDEX_ID=3454808470983802880        (display name: tender-rag-index)
#   VERTEX_INDEX_ENDPOINT_ID=6462051937788362752 (display name: tender-rag-endpoint)
# Store them in Secret Manager or environment templates as appropriate.
```

Grant the Google Drive integration permission by sharing the destination folder
with `sa-artifact@tender-automation-1008.iam.gserviceaccount.com`. The shared
drive "Tenders" uses folder ID `0AIIJEYSn69gTUk9PVA`; expose it to workloads via
the `GOOGLE_DRIVE_PARENT_FOLDER_ID` environment variable or a Secret Manager
entry.

## Attach the Accounts to Cloud Run Services

After updating IAM, redeploy or patch each Cloud Run service so it uses the
matching account:

```bash
REGION=us-central1

declare -A SERVICES=(
  [tender-backend]=sa-backend
  [ingest-api]=sa-ingest
  [pipeline-orchestrator]=sa-orchestrator
  [extractor-deadlines]=sa-extractor-deadlines
  [extractor-emd]=sa-extractor-emd
  [extractor-requirements]=sa-extractor-requirements
  [extractor-penalties]=sa-extractor-penalties
  [extractor-annexures]=sa-extractor-annexures
  [artifact-annexures]=sa-artifact
  [rag-indexer]=sa-rag
  [qa-loop]=sa-qa-loop
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
gcloud run services describe ingest-api \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --format="value(spec.template.spec.serviceAccountName)"
```

## Retire the Legacy Editor Account

Once every service runs with its dedicated account, strip `roles/editor` from
the default Compute Engine service account:

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

Log the command output in change-management tickets or deployment notes so the
access shift is recorded for compliance.
