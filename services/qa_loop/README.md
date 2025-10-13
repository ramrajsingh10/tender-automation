# QA Loop Service

Placeholder service representing the QA / retry controller. It accepts pipeline
tasks and immediately acknowledges them. Replace its logic when the real QA
workflow is implemented.

## Local Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
uvicorn main:app --reload
```

## Endpoints

- `POST /qa` — returns `{"status": "ack"}` and echoes the payload.

## Deployment

Run the service with the scoped account documented in
[`docs/service-accounts.md`](../../docs/service-accounts.md):

```bash
gcloud run deploy qa-loop \
  --image gcr.io/$PROJECT_ID/qa-loop \
  --region us-central1 \
  --service-account sa-qa-loop@tender-automation-1008.iam.gserviceaccount.com \
  --no-allow-unauthenticated
```
