from __future__ import annotations
import asyncio
import base64
import json
import logging
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import httpx
from fastapi import FastAPI, HTTPException, Request, status
from google.auth import exceptions as auth_exceptions
from google.cloud import firestore, storage
from google.cloud.firestore import Client as FirestoreClient
from google.protobuf.json_format import MessageToDict
from pydantic import BaseModel, Field
import vertexai
from vertexai.preview.generative_models import GenerativeModel, GenerationConfig
from pipeline import DEFAULT_PIPELINE, Task, build_pipeline_run_document
try:
    from google.cloud import aiplatform_v1beta1  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    aiplatform_v1beta1 = None  # type: ignore[assignment]
logger = logging.getLogger(__name__)
def _load_service_map() -> dict[str, str]:
    """Compile service endpoint overrides from environment variables."""
    base_map = {
        "ingest-api": os.getenv("INGEST_API_URL", ""),
        "extractor.deadlines": os.getenv("DEADLINES_EXTRACTOR_URL", ""),
        "extractor.emd": os.getenv("EMD_EXTRACTOR_URL", ""),
        "extractor.requirements": os.getenv("REQUIREMENTS_EXTRACTOR_URL", ""),
        "extractor.penalties": os.getenv("PENALTIES_EXTRACTOR_URL", ""),
        "extractor.annexures": os.getenv("ANNEXURES_EXTRACTOR_URL", ""),
        "artifact.annexures": os.getenv("ARTIFACT_ANNEXURES_URL", ""),
        "artifact.checklist": os.getenv("ARTIFACT_CHECKLIST_URL", ""),
        "artifact.plan": os.getenv("ARTIFACT_PLAN_URL", ""),
        "rag.index": os.getenv("RAG_INDEX_URL", ""),
        "qa.loop": os.getenv("QA_LOOP_URL", ""),
    }
    json_overrides = os.getenv("SERVICE_ENDPOINTS_JSON")
    if json_overrides:
        try:
            base_map.update(json.loads(json_overrides))
        except json.JSONDecodeError:
            logger.warning("Invalid SERVICE_ENDPOINTS_JSON payload; ignoring.")
    return {key: value for key, value in base_map.items() if value}
@dataclass(frozen=True)
class Settings:
    project_id: str = os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT", "")
    pipeline_collection: str = os.getenv("PIPELINE_COLLECTION", "pipelineRuns")
    tenders_collection: str = os.getenv("TENDERS_COLLECTION", "tenders")
    parsed_collection: str = os.getenv("PARSED_COLLECTION", "parsedDocuments")
    service_map: dict[str, str] = None  # type: ignore[assignment]
    vertex_rag_corpus_path: str = os.getenv("VERTEX_RAG_CORPUS_PATH", "")
    vertex_rag_location: str = os.getenv("VERTEX_RAG_CORPUS_LOCATION", "")
    vertex_rag_data_store_id: str = os.getenv("VERTEX_RAG_DATA_STORE_ID", "")
    vertex_rag_serving_config_id: str = os.getenv("VERTEX_RAG_SERVING_CONFIG_ID", "default_serving_config")
    vertex_rag_serving_config_path: str = os.getenv("VERTEX_RAG_SERVING_CONFIG_PATH", "")
    vertex_rag_default_branch: str = os.getenv("VERTEX_RAG_DEFAULT_BRANCH", "")
    vertex_rag_generative_model: str = os.getenv("VERTEX_RAG_GEMINI_MODEL", "gemini-2.5-flash")
    raw_bucket: str = os.getenv("RAW_TENDER_BUCKET", "rawtenderdata")
    parsed_bucket: str = os.getenv("PARSED_TENDER_BUCKET", "parsedtenderdata")
settings = Settings(service_map=_load_service_map())
_firestore_client: FirestoreClient | None = None
_rag_data_client: Any | None = None
_storage_client: storage.Client | None = None
_rag_service_client: Any | None = None
_vertexai_init_context: Optional[Tuple[str, str]] = None
DEFAULT_PLAYBOOK = [
    {
        "id": "document_id",
        "question": "Extract the document identifier (tender ID / RFP ID / reference number) exactly as stated in the tender pack.",
    },
    {
        "id": "submission_deadlines",
        "question": "List every submission-related deadline (bid submission, pre-bid queries, fee payments, etc.) with dates and times if available.",
    },
]
class PlaybookQuestion(BaseModel):
    id: str
    question: str
class RagPlaybookRequest(BaseModel):
    tenderId: str
    gcsUris: List[str]
    questions: Optional[List[PlaybookQuestion]] = None
    forgetAfterRun: bool = True
    pageSize: int | None = None
    class Config:
        populate_by_name = True
class RagPlaybookResult(BaseModel):
    questionId: str
    question: str
    answers: List["RagAnswer"]
    documents: List["RagDocument"]
class RagPlaybookResponse(BaseModel):
    results: List[RagPlaybookResult]
    outputUri: Optional[str] = None
class RagQueryRequest(BaseModel):
    tenderId: str
    question: str
    conversationId: str | None = None
    pageSize: int | None = None
    ragFileIds: List[str] | None = None

    class Config:
        populate_by_name = True


class RagCitation(BaseModel):
    startIndex: int | None = None
    endIndex: int | None = None
    sources: List[Dict[str, Any]] = Field(default_factory=list)


class RagAnswer(BaseModel):
    text: str
    citations: List[RagCitation] = Field(default_factory=list)


class RagDocument(BaseModel):
    id: str | None = None
    uri: str | None = None
    title: str | None = None
    snippet: str | None = None
    metadata: Dict[str, Any] | None = None


class RagQueryResponse(BaseModel):
    answers: List[RagAnswer] = Field(default_factory=list)
    documents: List[RagDocument] = Field(default_factory=list)


def get_firestore_client() -> FirestoreClient:
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client
    try:
        _firestore_client = firestore.Client(project=settings.project_id or None)
    except auth_exceptions.DefaultCredentialsError as exc:
        raise RuntimeError(
            "Firestore credentials not configured. Set GOOGLE_APPLICATION_CREDENTIALS or "
            "FIRESTORE_EMULATOR_HOST before starting the orchestrator service."
        ) from exc
    return _firestore_client
def _get_storage_client() -> storage.Client:
    global _storage_client
    if _storage_client is not None:
        return _storage_client
    try:
        _storage_client = storage.Client(project=settings.project_id or None)
    except auth_exceptions.DefaultCredentialsError as exc:
        raise RuntimeError(
            "Google Cloud Storage credentials not configured. Set GOOGLE_APPLICATION_CREDENTIALS "
            "or STORAGE_EMULATOR_HOST before starting the orchestrator service."
        ) from exc
    return _storage_client
def _extract_location_from_path(resource_path: str) -> str | None:
    if not resource_path:
        return None
    match = re.search(r"/locations/([^/]+)/", resource_path)
    if not match:
        return None
    location = match.group(1)
    return location or None
def _extract_project_from_resource(resource_path: str) -> str | None:
    if not resource_path:
        return None
    match = re.search(r"projects/([^/]+)/", resource_path)
    if not match:
        return None
    return match.group(1)
def _ensure_vertexai_initialized(project_id: str, location: str) -> None:
    global _vertexai_init_context
    if _vertexai_init_context != (project_id, location):
        vertexai.init(project=project_id, location=location)
        _vertexai_init_context = (project_id, location)
def _get_rag_data_client():
    global _rag_data_client
    if aiplatform_v1beta1 is None:
        raise RuntimeError(
            "google-cloud-aiplatform is not installed. Add it to services/orchestrator/requirements.txt."
        )
    if not settings.vertex_rag_corpus_path:
        raise RuntimeError("VERTEX_RAG_CORPUS_PATH environment variable is not configured.")
    if _rag_data_client is not None:
        return _rag_data_client
    client_options = None
    if settings.vertex_rag_location:
        client_options = {"api_endpoint": f"{settings.vertex_rag_location}-aiplatform.googleapis.com"}
    _rag_data_client = aiplatform_v1beta1.VertexRagDataServiceClient(client_options=client_options)
    return _rag_data_client
def _get_rag_service_client():
    global _rag_service_client
    if aiplatform_v1beta1 is None:
        raise RuntimeError(
            "google-cloud-aiplatform is not installed. Add it to services/orchestrator/requirements.txt."
        )
    if _rag_service_client is not None:
        return _rag_service_client
    endpoint = None
    if settings.vertex_rag_location:
        endpoint = f"{settings.vertex_rag_location}-aiplatform.googleapis.com"
    client_options = {"api_endpoint": endpoint} if endpoint else None
    _rag_service_client = aiplatform_v1beta1.VertexRagServiceClient(client_options=client_options)
    return _rag_service_client
def _run_generative_agent(
    project_id: str, location: str, question: str, contexts: List[Any]
) -> tuple[str, Optional[str]]:
    _ensure_vertexai_initialized(project_id, location)
    model_id = settings.vertex_rag_generative_model or "gemini-2.5-flash"
    model = GenerativeModel(model_id)
    if contexts:
        context_sections = []
        for idx, ctx in enumerate(contexts, start=1):
            ctx_text = getattr(ctx, "text", "") or ""
            source = getattr(ctx, "source_uri", "") or ""
            if ctx_text:
                context_sections.append(f"[Source {idx}] URI: {source}\n{ctx_text}")
        prompt_context = "\n\n".join(context_sections)
    else:
        prompt_context = "(no context)"
    instruction = (
        "Return the exact text span from the context that answers the question. "
        "Do not paraphrase or summarize. If no relevant span is present, respond with NOT_FOUND."
    )
    user_prompt = f"{instruction}\n\nQuestion:\n{question}\n\nContext:\n{prompt_context}"
    try:
        response = model.generate_content(
            user_prompt,
            generation_config=GenerationConfig(temperature=0.0, max_output_tokens=256),
        )
        answer_text = (getattr(response, "text", "") or "").strip()
    except Exception as exc:  # pragma: no cover - generative call failed
        logger.warning("Gemini extraction failed: %s", exc)
        answer_text = ""
    if not answer_text or answer_text.upper() == "NOT_FOUND":
        return "", None
    answer_lower = answer_text.lower()
    matched_source: Optional[str] = None
    for ctx in contexts:
        ctx_text = (getattr(ctx, "text", "") or "").lower()
        if answer_lower in ctx_text:
            matched_source = getattr(ctx, "source_uri", "") or None
            if matched_source:
                break
    if not matched_source:
        for ctx in contexts:
            src = getattr(ctx, "source_uri", "") or None
            if src:
                matched_source = src
                break
    return answer_text, matched_source
def _service_endpoint(task_target: str) -> str | None:
    return (settings.service_map or {}).get(task_target)
def _map_rag_files_by_uri() -> Dict[str, str]:
    if not settings.vertex_rag_corpus_path:
        return {}
    client = _get_rag_data_client()
    mapping: Dict[str, str] = {}
    for rag_file in client.list_rag_files(parent=settings.vertex_rag_corpus_path):
        gcs_source = getattr(rag_file, "gcs_source", None)
        uri = getattr(gcs_source, "uri", None)
        if uri:
            mapping[uri] = rag_file.name
    return mapping
def _import_rag_files(gcs_uris: List[str]) -> List[str]:
    if not gcs_uris:
        return []
    client = _get_rag_data_client()
    before = _map_rag_files_by_uri()
    request = aiplatform_v1beta1.ImportRagFilesRequest(
        parent=settings.vertex_rag_corpus_path,
        import_rag_files_config={"gcs_source": {"uris": gcs_uris}},
    )
    operation = client.import_rag_files(request=request)
    operation.result()
    after = _map_rag_files_by_uri()
    created: List[str] = []
    for uri in gcs_uris:
        name = after.get(uri)
        if name and before.get(uri) != name:
            created.append(name)
    return created
def _delete_rag_files(rag_file_names: List[str]) -> None:
    if not rag_file_names:
        return
    client = _get_rag_data_client()
    for name in rag_file_names:
        try:
            client.delete_rag_file(name=name)
        except Exception as exc:  # pragma: no cover - best effort cleanup
            logger.warning("Failed to delete rag file %s: %s", name, exc)
def _write_results_to_gcs(tender_id: str, payload: Dict[str, Any]) -> str:
    client = _get_storage_client()
    bucket = client.bucket(settings.parsed_bucket)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    object_name = f"{tender_id}/rag/results-{timestamp}.json"
    blob = bucket.blob(object_name)
    blob.cache_control = "no-store"
    blob.upload_from_string(
        json.dumps(payload, ensure_ascii=False, indent=2),
        content_type="application/json",
    )
    return f"gs://{settings.parsed_bucket}/{object_name}"
def _resolve_playbook_questions(questions: Optional[List[PlaybookQuestion]]) -> List[PlaybookQuestion]:
    if questions:
        return questions
    return [PlaybookQuestion(**item) for item in DEFAULT_PLAYBOOK]
def _run_playbook(request: RagPlaybookRequest) -> RagPlaybookResponse:
    questions = _resolve_playbook_questions(request.questions)
    rag_files: List[str] = []
    imported_via_corpus = False
    if request.gcsUris:
        if settings.vertex_rag_corpus_path:
            rag_files = _import_rag_files(request.gcsUris)
            imported_via_corpus = True
        elif not (settings.vertex_rag_data_store_id or settings.vertex_rag_default_branch):
            raise RuntimeError(
                "No RAG backend configured for ingestion; set VERTEX_RAG_DATA_STORE_ID or VERTEX_RAG_CORPUS_PATH."
            )
        else:
            logger.debug(
                "Skipping direct RagFile import for tender %s; relying on Discovery Engine data store contents.",
                request.tenderId,
            )
    results: List[RagPlaybookResult] = []
    for question in questions:
        query_response = _execute_vertex_search(
            RagQueryRequest(
                tenderId=request.tenderId,
                question=question.question,
                pageSize=request.pageSize,
                ragFileIds=rag_files or None,
            )
        )
        results.append(
            RagPlaybookResult(
                questionId=question.id,
                question=question.question,
                answers=query_response.answers,
                documents=query_response.documents,
            )
        )
    payload = {
        "tenderId": request.tenderId,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "results": [result.model_dump(mode="json") for result in results],
    }
    output_uri = _write_results_to_gcs(request.tenderId, payload)
    if request.forgetAfterRun and imported_via_corpus:
        if not rag_files:
            # Fall back to resolving existing RagFiles for the provided URIs.
            rag_files = [
                name for uri, name in _map_rag_files_by_uri().items() if uri in request.gcsUris
            ]
        _delete_rag_files([name for name in rag_files if name])
    return RagPlaybookResponse(results=results, outputUri=output_uri)
def create_app() -> FastAPI:
    app = FastAPI(
        title="Tender Pipeline Orchestrator",
        description="Coordinates extraction, QA, and artifact generation tasks.",
        version="0.1.0",
    )
    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}
    @app.post("/rag/query", tags=["rag"])
    async def rag_query(request: RagQueryRequest) -> RagQueryResponse:
        if not settings.vertex_rag_corpus_path:
            raise HTTPException(
                status_code=503,
                detail="Vertex RAG corpus is not configured. Set VERTEX_RAG_CORPUS_PATH.",
            )
        try:
            payload = _execute_vertex_search(request)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("RAG query failed for tender %s.", request.tenderId)
            raise HTTPException(status_code=502, detail=f"Vertex Agent Builder query failed: {exc}") from exc
        return payload
    @app.post("/rag/playbook", tags=["rag"])
    async def rag_playbook(request: RagPlaybookRequest) -> RagPlaybookResponse:
        if not request.gcsUris:
            raise HTTPException(status_code=400, detail="gcsUris must include at least one Cloud Storage uri.")
        try:
            response = _run_playbook(request)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Playbook execution failed for tender %s.", request.tenderId)
            raise HTTPException(status_code=502, detail=f"Failed to run playbook: {exc}") from exc
        return response
    @app.post("/pubsub/pipeline-trigger", status_code=status.HTTP_202_ACCEPTED)
    async def handle_pubsub(request: Request) -> dict[str, Any]:
        payload = await request.json()
        message = payload.get("message")
        if not message or "data" not in message:
            raise HTTPException(status_code=400, detail="Invalid Pub/Sub message payload.")
        try:
            data_bytes = base64.b64decode(message["data"])
            trigger_payload = json.loads(data_bytes)
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Failed to decode Pub/Sub message.") from exc
        tender_id = trigger_payload.get("tenderId")
        ingest_job_id = trigger_payload.get("ingestJobId")
        if not tender_id or not ingest_job_id:
            raise HTTPException(status_code=400, detail="Missing tenderId or ingestJobId in message.")
        run_id = datetime.now(timezone.utc).isoformat()
        run_document = build_pipeline_run_document(
            definition=DEFAULT_PIPELINE,
            run_id=run_id,
            tender_id=tender_id,
            trigger=trigger_payload.get("trigger", "ingest"),
            ingest_job_id=ingest_job_id,
        )
        firestore_client = get_firestore_client()
        pipeline_doc = firestore_client.collection(settings.pipeline_collection).document(tender_id)
        now = datetime.now(timezone.utc).isoformat()
        pipeline_doc.set(
            {
                "tenderId": tender_id,
                "latestRunId": run_id,
                "updatedAt": now,
            },
            merge=True,
        )
        run_ref = pipeline_doc.collection("runs").document(run_id)
        run_ref.set(run_document)
        firestore_client.collection(settings.tenders_collection).document(tender_id).set(
            {"tenderId": tender_id, "pipelineRunId": run_id, "lastUpdated": now},
            merge=True,
        )
        await _execute_pipeline(firestore_client, run_ref, run_document)
        logger.info("Queued pipeline run %s for tender %s.", run_id, tender_id)
        return {"status": "queued", "tenderId": tender_id, "runId": run_id}
    return app
app = create_app()
async def _execute_pipeline(
    firestore_client: FirestoreClient,
    run_ref: firestore.DocumentReference,
    run_document: dict[str, Any],
) -> None:
    try:
        tender_id = run_ref.parent.parent.id
        normalized_document = _load_normalized_document(firestore_client, tender_id)
    except KeyError as exc:
        run_ref.update(
            {
                "status": "failed",
                "error": str(exc),
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
        )
        return
    tasks_state = run_document["tasks"]
    current_stage = run_document["currentStage"]
    grouped = DEFAULT_PIPELINE.grouped_tasks
    while current_stage in grouped:
        stage_tasks = grouped[current_stage]
        pending = [task for task in stage_tasks if tasks_state[task.task_id]["status"] in {"pending", "retry"}]
        if not pending:
            current_stage += 1
            run_ref.update({"currentStage": current_stage, "updatedAt": datetime.now(timezone.utc).isoformat()})
            continue
        if stage_tasks[0].stage == "parallel":
            results = await _run_tasks_concurrently(run_ref, pending, normalized_document)
        else:
            results = [await _run_task(run_ref, task, normalized_document) for task in pending]
        if any(result == "failed" for result in results):
            run_ref.update({"status": "failed", "updatedAt": datetime.now(timezone.utc).isoformat()})
            return
    run_ref.update({"status": "succeeded", "updatedAt": datetime.now(timezone.utc).isoformat()})
async def _run_tasks_concurrently(
    run_ref: firestore.DocumentReference,
    tasks: list[Task],
    normalized_document: dict[str, Any],
) -> list[str]:
    async with httpx.AsyncClient(timeout=30) as client:
        coros = [_run_task(run_ref, task, normalized_document, client) for task in tasks]
        return await asyncio.gather(*coros)
async def _run_task(
    run_ref: firestore.DocumentReference,
    task: Task,
    normalized_document: dict[str, Any],
    client: httpx.AsyncClient | None = None,
) -> str:
    task_path = f"tasks.{task.task_id}"
    task_state = run_ref.get().to_dict()["tasks"][task.task_id]
    endpoint = _service_endpoint(task.target)
    if not endpoint:
        run_ref.update(
            {
                f"{task_path}.status": "skipped",
                f"{task_path}.skippedAt": datetime.now(timezone.utc).isoformat(),
                f"{task_path}.note": "No endpoint configured.",
            }
        )
        return "skipped"
    run_ref.update(
        {
            f"{task_path}.status": "in-progress",
            f"{task_path}.startedAt": datetime.now(timezone.utc).isoformat(),
        }
    )
    payload = {
        "tenderId": run_ref.parent.parent.id,
        "taskId": task.task_id,
        "target": task.target,
        "document": normalized_document,
    }
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=30) as session:
                response = await session.post(endpoint, json=payload)
        else:
            response = await client.post(endpoint, json=payload)
        response.raise_for_status()
        run_ref.update({f"{task_path}.status": "succeeded", f"{task_path}.completedAt": datetime.now(timezone.utc).isoformat()})
        return "succeeded"
    except Exception as exc:
        retries = task_state.get("retries", 0) + 1
        run_ref.update(
            {
                f"{task_path}.status": "retry" if retries < 3 else "failed",
                f"{task_path}.error": str(exc),
                f"{task_path}.retries": retries,
                "status": "running",
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
        )
        return "retry" if retries < 3 else "failed"
def _load_normalized_document(firestore_client: FirestoreClient, tender_id: str) -> dict[str, Any]:
    doc = firestore_client.collection(settings.parsed_collection).document(tender_id).get()
    if not doc.exists:
        raise KeyError(f"Normalized document for tender {tender_id} not found.")
    payload = doc.to_dict()
    if not isinstance(payload, dict):
        raise KeyError(f"Normalized document for tender {tender_id} is malformed.")
    return payload
def _execute_vertex_search(request: RagQueryRequest) -> RagQueryResponse:
    client = _get_rag_service_client()
    if not settings.vertex_rag_corpus_path:
        raise RuntimeError("VERTEX_RAG_CORPUS_PATH is not configured.")
    location = settings.vertex_rag_location or _extract_location_from_path(settings.vertex_rag_corpus_path)
    if not location:
        raise RuntimeError("Unable to determine Vertex RAG location. Set VERTEX_RAG_CORPUS_LOCATION.")
    project_id = settings.project_id or _extract_project_from_resource(settings.vertex_rag_corpus_path)
    if not project_id:
        raise RuntimeError("Unable to determine GCP project for Vertex RAG requests.")
    rag_resource = aiplatform_v1beta1.RetrieveContextsRequest.VertexRagStore.RagResource(
        rag_corpus=settings.vertex_rag_corpus_path,
    )
    if request.ragFileIds:
        rag_resource.rag_file_ids.extend(request.ragFileIds)
    vertex_rag_store = aiplatform_v1beta1.RetrieveContextsRequest.VertexRagStore(
        rag_resources=[rag_resource]
    )
    rag_query = aiplatform_v1beta1.RagQuery(
        text=request.question,
        similarity_top_k=request.pageSize or 5,
    )
    parent = f"projects/{project_id}/locations/{location}"
    response = client.retrieve_contexts(
        request=aiplatform_v1beta1.RetrieveContextsRequest(
            parent=parent,
            query=rag_query,
            vertex_rag_store=vertex_rag_store,
        )
    )
    contexts = list(getattr(response.contexts, "contexts", []))
    if not contexts:
        return RagQueryResponse(answers=[RagAnswer(text="No relevant context found.", citations=[])], documents=[])
    documents: List[RagDocument] = []
    sources_seen: set[str] = set()
    for ctx in contexts:
        source_uri = getattr(ctx, "source_uri", "") or ""
        text = getattr(ctx, "text", "") or ""
        distance = getattr(ctx, "distance", None)
        metadata = {"distance": distance} if distance is not None else None
        if source_uri not in sources_seen:
            documents.append(
                RagDocument(
                    id=source_uri or None,
                    uri=source_uri or None,
                    title=source_uri.split("/")[-1] if source_uri else None,
                    snippet=text[:400],
                    metadata=metadata,
                )
            )
            sources_seen.add(source_uri)
    answer_text, citation_source = _run_generative_agent(project_id, location, request.question, contexts)
    if not answer_text.strip():
        answer_text = "No relevant context found."
    citations: List[RagCitation] = []
    if citation_source:
        citations.append(
            RagCitation(
                startIndex=None,
                endIndex=None,
                sources=[{"sourceUri": citation_source}],
            )
        )
    answers = [RagAnswer(text=answer_text, citations=citations)]
    return RagQueryResponse(answers=answers, documents=documents)


