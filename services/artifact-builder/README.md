# Artifact Builder

Generates high-fidelity annexures, compliance checklists, and baseline project plans.

Phase 1 focuses on annexure reproduction. Each annexure is extracted from the
original tender PDF and uploaded to Google Docs as an independent document while
preserving layout (tables, symbols, images).

## Responsibilities

- Reconstruct annexure documents with original symbols/images and upload them as
  Google Docs files (one doc per annexure).
- Generate compliance checklists and baseline project plans from approved facts.
- Publish artifacts to `gs://tender-artifacts/{tenderId}/{artifactType}/{version}/`.
- Update Firestore `artifacts` collection with metadata (Google Doc ID/link,
  annexure ID, source provenance, versions).
- Future stages (`artifact.checklist`, `artifact.plan`) will reuse the same
  pattern once the compliance generator is implemented (see
  `docs/compliance-plan.md`).

## Implementation Notes

- Use `pikepdf` for page extraction, Google Cloud Storage for downloading the
  raw PDF, and the Google Drive API to import pages as Google Docs documents.
- `GOOGLE_DRIVE_PARENT_FOLDER_ID` controls where docs are stored. Service
  account credentials (Application Default Credentials) must have Drive access.
- Artifacts are stored in Firestore under `artifacts/{id}` and can also be
  mirrored to Cloud Storage if required.

## Deployment

Run the Cloud Run service as
`sa-artifact@tender-automation-1008.iam.gserviceaccount.com` and make sure it is
granted the roles listed in [`docs/service-accounts.md`](../../docs/service-accounts.md):
`roles/datastore.user`, `roles/storage.objectViewer`, and `roles/drive.file`.
Share the Google Drive destination folder with the same account before
deploying.

```bash
gcloud run deploy artifact-annexures \
  --image gcr.io/$PROJECT_ID/artifact-annexures \
  --region us-central1 \
  --service-account sa-artifact@tender-automation-1008.iam.gserviceaccount.com \
  --no-allow-unauthenticated
```

### Google Drive configuration

Artifacts are written to the shared drive “Tenders”. The root folder ID is
`0AIIJEYSn69gTUk9PVA`. Propagate it via the `GOOGLE_DRIVE_PARENT_FOLDER_ID`
environment variable:

```bash
export GOOGLE_DRIVE_PARENT_FOLDER_ID=0AIIJEYSn69gTUk9PVA
```

For Cloud Run, prefer Secret Manager:

```bash
PROJECT_ID=tender-automation-1008
echo -n "0AIIJEYSn69gTUk9PVA" | \
  gcloud secrets create google-drive-parent-folder-id --data-file=- --project $PROJECT_ID

gcloud run services update artifact-annexures \
  --region us-central1 \
  --service-account sa-artifact@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-secrets GOOGLE_DRIVE_PARENT_FOLDER_ID=google-drive-parent-folder-id:latest \
  --project $PROJECT_ID
```

If the secret already exists, skip `create` and add a new version with
`gcloud secrets versions add ...`.
