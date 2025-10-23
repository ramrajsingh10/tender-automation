from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from google.auth import exceptions as auth_exceptions
from google.cloud import firestore, storage
from google.cloud.firestore import Client as FirestoreClient
from google.protobuf.json_format import MessageToDict
from pydantic import BaseModel, Field

from pipeline import DEFAULT_PIPELINE, Task, build_pipeline_run_document

try:
    from google.cloud import discoveryengine_v1beta, aiplatform_v1beta1  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    discoveryengine_v1beta = None  # type: ignore[assignment]
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
    raw_bucket: str = os.getenv("RAW_TENDER_BUCKET", "rawtenderdata")
    parsed_bucket: str = os.getenv("PARSED_TENDER_BUCKET", "parsedtenderdata")


settings = Settings(service_map=_load_service_map())
_firestore_client: FirestoreClient | None = None
_search_client: Any | None = None
_rag_data_client: Any | None = None
_storage_client: storage.Client | None = None


DEFAULT_PLAYBOOK = [
    {
        "id": "overview",
        "question": "Provide a concise summary of this tender, highlighting the procuring entity, objective, and key deliverables.",
    },
    {
        "id": "submission_deadline",
        "question": "What is the submission deadline for this tender? Include date and time if specified.",
    },
    {
        "id": "emd_amount",
        "question": "What is the Earnest Money Deposit (EMD) amount required? Specify the currency and any payment notes.",
    },
    {
        "id": "prebid_meeting",
        "question": "Is there a pre-bid meeting? Provide the scheduled date, time, and location if available.",
    },
    {
        "id": "penalties",
        "question": "Summarize any penalty or liquidated damages clauses mentioned in the tender.",
    },
    {
        "id": "technical_requirements",
        "question": "List the key technical or eligibility requirements for bidders.",
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
        if not settings.vertex_rag_data_store_id:
            raise HTTPException(
                status_code=503,
                detail="Vertex Agent Builder serving config is not configured. Set VERTEX_RAG_DATA_STORE_ID.",
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


def _get_search_client() -> Any:
    global _search_client
    if discoveryengine_v1beta is None:
        raise RuntimeError(
            "google-cloud-discoveryengine is not installed. Add it to requirements.txt for the orchestrator service."
        )
    if _search_client is not None:
        return _search_client
    location_hint = (
        _extract_location_from_path(settings.vertex_rag_serving_config_path)
        or _extract_location_from_path(settings.vertex_rag_data_store_id)
        or settings.vertex_rag_location
    )
    endpoint = None
    if location_hint and location_hint != "global":
        endpoint = f"{location_hint}-discoveryengine.googleapis.com"
    client_options = {"api_endpoint": endpoint} if endpoint else None
    _search_client = discoveryengine_v1beta.SearchServiceClient(client_options=client_options)
    return _search_client


def _execute_vertex_search(request: RagQueryRequest) -> RagQueryResponse:
    client = _get_search_client()
    serving_config = settings.vertex_rag_serving_config_path
    serving_config_id = settings.vertex_rag_serving_config_id or "default_serving_config"
    if not serving_config:
        data_store_id = settings.vertex_rag_data_store_id
        if not data_store_id:
            raise RuntimeError("VERTEX_RAG_DATA_STORE_ID is not configured.")
        if "/" in data_store_id:
            normalized = data_store_id.rstrip("/")
            serving_config = f"{normalized}/servingConfigs/{serving_config_id}"
        else:
            project = settings.project_id
            if not project:
                raise RuntimeError(
                    "GCP_PROJECT or GOOGLE_CLOUD_PROJECT must be set to build Discovery Engine serving config path."
                )
            location = settings.vertex_rag_location or "global"
            serving_config = discoveryengine_v1beta.SearchServiceClient.serving_config_path(
                project,
                location,
                data_store_id,
                serving_config_id,
            )

    summary_spec = discoveryengine_v1beta.SearchRequest.ContentSearchSpec.SummarySpec(
        summary_result_count=1,
        include_citations=True,
    )
    search_request = discoveryengine_v1beta.SearchRequest(
        serving_config=serving_config,
        query=request.question,
        page_size=request.pageSize or 5,
        content_search_spec=discoveryengine_v1beta.SearchRequest.ContentSearchSpec(
            summary_spec=summary_spec
        ),
    )
    if request.conversationId:
        search_request.user_pseudo_id = request.conversationId

    iterator = client.search(request=search_request)
    results = list(iterator)

    summary = getattr(iterator, "summary", None)
    answers: List[RagAnswer] = []
    if summary and summary.summary_text:
        citations: List[RagCitation] = []
        for meta in summary.summary_with_metadata:
            meta_dict = MessageToDict(meta, preserving_proto_field_name=True)
            citation_meta = meta_dict.get("citationMetadata", {})
            references = meta_dict.get("references", [])
            for citation_entry in citation_meta.get("citations", []):
                sources: List[Dict[str, Any]] = []
                for source in citation_entry.get("sources", []):
                    ref_index = source.get("referenceIndex")
                    ref_payload = references[ref_index] if isinstance(ref_index, int) and ref_index < len(references) else {}
                    sources.append(
                        {
                            "reference": ref_payload,
                            "pageIdentifier": source.get("pageIdentifier"),
                        }
                    )
                citations.append(
                    RagCitation(
                        startIndex=citation_entry.get("startIndex"),
                        endIndex=citation_entry.get("endIndex"),
                        sources=sources,
                    )
                )
        answers.append(RagAnswer(text=summary.summary_text, citations=citations))

    documents: List[RagDocument] = []
    for result in results:
        document = result.document
        derived = (
            MessageToDict(document.derived_struct_data, preserving_proto_field_name=True)
            if document.derived_struct_data
            else {}
        )
        struct = (
            MessageToDict(document.struct_data, preserving_proto_field_name=True)
            if document.struct_data
            else {}
        )
        content_uri = document.content.uri if document.content and getattr(document.content, "uri", None) else None
        snippet = derived.get("snippet") or struct.get("snippet")
        documents.append(
            RagDocument(
                id=document.id or result.id or document.name,
                uri=content_uri or derived.get("uri"),
                title=derived.get("title") or struct.get("title"),
                snippet=snippet,
                metadata=derived or struct or None,
            )
        )

    return RagQueryResponse(answers=answers, documents=documents)
