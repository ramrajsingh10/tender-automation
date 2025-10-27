## Active Services

- **ingest-worker**  
  Primary URL: https://ingest-worker-981270825391.us-central1.run.app  
  Notes: Receives upload completion notifications and imports bundles into Vertex RAG.

- **orchestrator**  
  Primary URL: https://orchestrator-981270825391.us-central1.run.app  
  Notes: Runs Gemini playbooks, handles `/rag/query`, writes results to Cloud Storage.

- **tender-backend**  
  Primary URL: https://tender-backend-981270825391.us-central1.run.app  
  Notes: Public API for uploads, ingestion status, playbook triggers, and ad-hoc RAG questions.

- **tender-automation (Firebase Hosting)**  
  Primary URL: https://tender-automation-1008.web.app  
  SSR Function (internal): https://ssrtenderautomation1008-981270825391.us-central1.run.app

## Managed RAG Corpus

- Resource path: `projects/tender-automation-1008/locations/us-east4/ragCorpora/6917529027641081856`  
- Embedding model: `text-multilingual-embedding-002`
