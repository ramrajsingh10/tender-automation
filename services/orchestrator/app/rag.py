from __future__ import annotations

import logging
import statistics
import time
from collections.abc import Iterable
from threading import Lock
from typing import Dict, List, Tuple, Optional, Set

from google.api_core import exceptions as google_exceptions
from google.protobuf.json_format import MessageToDict

try:
    from google.cloud import aiplatform_v1beta1  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    aiplatform_v1beta1 = None  # type: ignore[assignment]

from .clients import get_rag_data_client, get_rag_service_client
from .config import settings
from .models import AnswerEvidence, RagDocument, RagQueryRequest, RagQueryResponse, RagAnswer, RagCitation
from .generative import run_generative_agent

logger = logging.getLogger(__name__)
_rag_file_filter_supported: bool = True
_retrieval_cache: Dict[Tuple, Tuple[float, List[object]]] = {}
_cache_lock: Lock = Lock()


def rag_file_name_to_id(resource_name: str) -> str:
    if not resource_name:
        return resource_name
    return resource_name.rsplit("/", 1)[-1]


def map_rag_files_by_uri() -> Dict[str, str]:
    if not settings.vertex_rag_corpus_path:
        return {}
    client = get_rag_data_client()
    mapping: Dict[str, str] = {}
    for rag_file in client.list_rag_files(parent=settings.vertex_rag_corpus_path):
        gcs_source = getattr(rag_file, "gcs_source", None)
        if not gcs_source:
            continue
        candidates: Iterable[str] = []
        explicit_uri = getattr(gcs_source, "uri", None)
        if explicit_uri:
            candidates = [explicit_uri]
        else:
            uris_attr = getattr(gcs_source, "uris", None)
            if isinstance(uris_attr, Iterable):
                candidates = [str(item) for item in uris_attr]
        for uri in candidates:
            if uri:
                mapping[str(uri)] = rag_file.name
    return mapping


def import_rag_files(gcs_uris: List[str]) -> Dict[str, str]:
    if not gcs_uris:
        return {}
    client = get_rag_data_client()
    import_config: Dict[str, object] = {"gcs_source": {"uris": gcs_uris}}
    if settings.vertex_rag_chunk_size_tokens > 0:
        chunk_kwargs: Dict[str, int] = {"chunk_size": settings.vertex_rag_chunk_size_tokens}
        if settings.vertex_rag_chunk_overlap_tokens > 0:
            chunk_kwargs["chunk_overlap"] = settings.vertex_rag_chunk_overlap_tokens
        import_config["rag_file_chunking_config"] = aiplatform_v1beta1.RagFileChunkingConfig(**chunk_kwargs)  # type: ignore[attr-defined]
    request = aiplatform_v1beta1.ImportRagFilesRequest(  # type: ignore[attr-defined]
        parent=settings.vertex_rag_corpus_path,
        import_rag_files_config=import_config,
    )
    operation = client.import_rag_files(request=request)
    operation.result()
    after = map_rag_files_by_uri()
    resolved: Dict[str, str] = {}
    for uri in gcs_uris:
        name = after.get(uri)
        if name:
            resolved[uri] = name
        else:
            logger.warning("RagFile missing for uri %s after import.", uri)
    return resolved


def _get_cache_key(
    tender_id: str,
    question: str,
    page_size: int,
    gcs_uris: Iterable[str],
    rag_file_ids: Iterable[str],
) -> Tuple:
    normalized_question = question.strip().lower()
    uris_tuple = tuple(sorted(gcs_uris))
    rag_ids_tuple = tuple(sorted(rag_file_ids))
    return (tender_id, normalized_question, page_size, uris_tuple, rag_ids_tuple)


def _get_cached_contexts(key: Tuple) -> List[object] | None:
    ttl = settings.vertex_rag_cache_ttl_seconds
    if ttl <= 0:
        return None
    now = time.time()
    with _cache_lock:
        entry = _retrieval_cache.get(key)
        if not entry:
            return None
        timestamp, contexts = entry
        if now - timestamp > ttl:
            _retrieval_cache.pop(key, None)
            return None
        return contexts


def _store_cached_contexts(key: Tuple, contexts: List[object]) -> None:
    ttl = settings.vertex_rag_cache_ttl_seconds
    if ttl <= 0:
        return
    now = time.time()
    with _cache_lock:
        _retrieval_cache[key] = (now, contexts)
        max_entries = max(settings.vertex_rag_cache_max_entries, 1)
        if len(_retrieval_cache) > max_entries:
            # Evict oldest entry (other than the one we just set)
            oldest_key = None
            oldest_ts = now
            for candidate_key, (candidate_ts, _) in _retrieval_cache.items():
                if candidate_key == key:
                    continue
                if oldest_key is None or candidate_ts < oldest_ts:
                    oldest_key = candidate_key
                    oldest_ts = candidate_ts
            if oldest_key is not None:
                _retrieval_cache.pop(oldest_key, None)


def delete_rag_files(rag_file_names: List[str]) -> Tuple[List[str], List[str]]:
    if not rag_file_names:
        return [], []
    client = get_rag_data_client()
    deleted: List[str] = []
    errors: List[str] = []
    for name in rag_file_names:
        try:
            client.delete_rag_file(name=name)
            deleted.append(name)
        except Exception as exc:  # pragma: no cover - best effort cleanup
            logger.warning("Failed to delete rag file %s: %s", name, exc)
            errors.append(f"{name}: {exc}")
    return deleted, errors


def _extract_location_from_path(resource_path: str) -> str | None:
    if not resource_path:
        return None
    marker = "/locations/"
    start = resource_path.find(marker)
    if start == -1:
        return None
    start += len(marker)
    end = resource_path.find("/", start)
    location = resource_path[start:] if end == -1 else resource_path[start:end]
    return location or None


def _extract_project_from_resource(resource_path: str) -> str | None:
    if not resource_path:
        return None
    marker = "projects/"
    start = resource_path.find(marker)
    if start == -1:
        return None
    start += len(marker)
    end = resource_path.find("/", start)
    project = resource_path[start:] if end == -1 else resource_path[start:end]
    return project or None


def execute_vertex_search(request: RagQueryRequest) -> Tuple[RagQueryResponse, List[object]]:
    global _rag_file_filter_supported
    client = get_rag_service_client()
    if not settings.vertex_rag_corpus_path:
        raise RuntimeError("VERTEX_RAG_CORPUS_PATH is not configured.")
    location = settings.vertex_rag_location or _extract_location_from_path(settings.vertex_rag_corpus_path)
    if not location:
        raise RuntimeError("Unable to determine Vertex RAG location. Set VERTEX_RAG_CORPUS_LOCATION.")
    project_id = settings.project_id or _extract_project_from_resource(settings.vertex_rag_corpus_path)
    if not project_id:
        raise RuntimeError("Unable to determine GCP project for Vertex RAG requests.")

    page_size = request.pageSize or settings.vertex_rag_default_top_k
    initial_gcs_uris = tuple(request.gcsUris)
    initial_rag_file_ids = tuple(request.ragFileIds or [])

    cache_key = _get_cache_key(request.tenderId, request.question, page_size, initial_gcs_uris, initial_rag_file_ids)
    cached_contexts = _get_cached_contexts(cache_key)
    cache_hit = cached_contexts is not None

    rag_resource = aiplatform_v1beta1.RetrieveContextsRequest.VertexRagStore.RagResource(  # type: ignore[attr-defined]
        rag_corpus=settings.vertex_rag_corpus_path,
    )
    rag_file_ids: List[str] = []
    if initial_rag_file_ids:
        rag_file_ids = [rag_file_name_to_id(rag_id) for rag_id in initial_rag_file_ids if rag_id]
        if rag_file_ids and _rag_file_filter_supported:
            rag_resource.rag_file_ids.extend(rag_file_ids)
    effective_gcs_uris: List[str] = list(initial_gcs_uris)
    if not effective_gcs_uris and initial_rag_file_ids:
        mapping = map_rag_files_by_uri()
        for uri, name in mapping.items():
            if name in initial_rag_file_ids and uri not in effective_gcs_uris:
                effective_gcs_uris.append(uri)
    vertex_rag_store = aiplatform_v1beta1.RetrieveContextsRequest.VertexRagStore(  # type: ignore[attr-defined]
        rag_resources=[rag_resource]
    )
    rag_query = aiplatform_v1beta1.RagQuery(  # type: ignore[attr-defined]
        text=request.question,
        similarity_top_k=page_size,
    )
    parent = f"projects/{project_id}/locations/{location}"
    retrieve_request = aiplatform_v1beta1.RetrieveContextsRequest(  # type: ignore[attr-defined]
        parent=parent,
        query=rag_query,
        vertex_rag_store=vertex_rag_store,
    )
    contexts: List[object]
    start_time = time.time()
    if cached_contexts is not None:
        contexts = list(cached_contexts)
    else:
        try:
            response = client.retrieve_contexts(request=retrieve_request)
        except google_exceptions.MethodNotImplemented as exc:
            if rag_file_ids and _rag_file_filter_supported:
                _rag_file_filter_supported = False
                logger.warning(
                    "Vertex RAG retrieve_contexts does not support ragFileIds filter; disabling filter. Error: %s",
                    exc,
                )
                retry_store = aiplatform_v1beta1.RetrieveContextsRequest.VertexRagStore(  # type: ignore[attr-defined]
                    rag_resources=[
                        aiplatform_v1beta1.RetrieveContextsRequest.VertexRagStore.RagResource(  # type: ignore[attr-defined]
                            rag_corpus=settings.vertex_rag_corpus_path,
                        )
                    ]
                )
                retry_request = aiplatform_v1beta1.RetrieveContextsRequest(  # type: ignore[attr-defined]
                    parent=parent,
                    query=rag_query,
                    vertex_rag_store=retry_store,
                )
                try:
                    response = client.retrieve_contexts(request=retry_request)
                except google_exceptions.MethodNotImplemented as inner_exc:
                    logger.warning(
                        "Vertex RAG retrieve_contexts not enabled for corpus %s; returning empty context. Error: %s",
                        settings.vertex_rag_corpus_path,
                        inner_exc,
                    )
                    return RagQueryResponse(answers=[], documents=[]), []
            else:
                logger.warning(
                    "Vertex RAG retrieve_contexts not enabled for corpus %s; returning empty context. Error: %s",
                    settings.vertex_rag_corpus_path,
                    exc,
                )
                return RagQueryResponse(answers=[], documents=[]), []

        contexts = list(getattr(response.contexts, "contexts", []))
        if contexts:
            _store_cached_contexts(cache_key, contexts)
        cache_hit = False

    elapsed = time.time() - start_time

    if not contexts:
        return RagQueryResponse(answers=[RagAnswer(text="No relevant context found.", citations=[])], documents=[]), []

    documents: List[RagDocument] = []
    sources_seen: set[str] = set()
    for ctx in contexts:
        source_uri = getattr(ctx, "source_uri", "") or ""
        text = getattr(ctx, "text", "") or ""
        distance = getattr(ctx, "distance", None)
        page_label = _extract_page_label(ctx)
        metadata: Dict[str, object] | None = {}
        if distance is not None:
            metadata["distance"] = distance
        if page_label:
            metadata["pageLabel"] = page_label
        if not metadata:
            metadata = None
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

    _log_retrieval_metrics(
        cache_hit=cache_hit,
        question=request.question,
        tender_id=request.tenderId,
        page_size=page_size,
        contexts=contexts,
    )
    logger.debug(
        "retrieval_duration tender=%s question=\"%s\" seconds=%.3f cache_hit=%s",
        request.tenderId,
        request.question,
        elapsed,
        cache_hit,
    )

    answer_text, citation_source = run_generative_agent(project_id, location, request.question, contexts)
    if not answer_text.strip():
        answer_text = "No relevant context found."
    citations: List[RagCitation] = []
    if citation_source:
        citations.append(RagCitation(startIndex=None, endIndex=None, sources=[{"sourceUri": citation_source}]))
    answers = [RagAnswer(text=answer_text, citations=citations)]
    populate_answer_evidence(answers, documents)
    return RagQueryResponse(answers=answers, documents=documents), contexts


def _estimate_token_length(text: str) -> int:
    """Rudimentary token estimate based on whitespace splitting."""
    if not text:
        return 0
    return len(text.split())


def _log_retrieval_metrics(
    *,
    cache_hit: bool,
    question: str,
    tender_id: str,
    page_size: int,
    contexts: List[object],
) -> None:
    char_lengths: List[int] = []
    token_lengths: List[int] = []
    sources: List[str] = []
    for ctx in contexts:
        ctx_text = getattr(ctx, "text", "") or ""
        char_lengths.append(len(ctx_text))
        token_lengths.append(_estimate_token_length(ctx_text))
        sources.append(getattr(ctx, "source_uri", "") or "")

    if not char_lengths:
        logger.info(
            "retrieval_result tender=%s question=\"%s\" page_size=%s cache_hit=%s contexts=0",
            tender_id,
            question,
            page_size,
            cache_hit,
        )
        return

    def _stats(values: List[int]) -> Tuple[int, float, float]:
        return (
            len(values),
            float(statistics.mean(values)),
            float(statistics.median(values)),
        )

    ctx_count, chars_mean, chars_median = _stats(char_lengths)
    _, tokens_mean, tokens_median = _stats(token_lengths)

    logger.info(
        "retrieval_result tender=%s question=\"%s\" page_size=%s cache_hit=%s contexts=%s chars_mean=%.1f chars_median=%.1f tokens_mean=%.1f tokens_median=%.1f unique_sources=%s",
        tender_id,
        question,
        page_size,
        cache_hit,
        ctx_count,
        chars_mean,
        chars_median,
        tokens_mean,
        tokens_median,
        len(set(sources)),
    )


def _extract_page_label(ctx: object) -> Optional[str]:
    def _normalize(value: object) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, list):
            for item in value:
                normalized = _normalize(item)
                if normalized:
                    return normalized
            return None
        if isinstance(value, dict):
            for key in ("page", "pageNumber", "page_number", "startPage", "endPage", "value"):
                if key in value:
                    normalized = _normalize(value[key])
                    if normalized:
                        return normalized
            return None
        value_str = str(value).strip()
        return value_str or None

    def _pull_from_dict(data: Dict[str, object]) -> Optional[str]:
        for key in (
            "page",
            "pageNumber",
            "page_number",
            "page_label",
            "pageLabel",
            "page_label_text",
            "pageNumbers",
            "page_numbers",
        ):
            if key in data:
                return _normalize(data[key])
        return None

    chunk_metadata = getattr(ctx, "chunk_metadata", None)
    if chunk_metadata is not None:
        candidate = _normalize(getattr(chunk_metadata, "page", None)) or _normalize(
            getattr(chunk_metadata, "page_number", None)
        )
        if candidate:
            return candidate
        try:
            chunk_dict = MessageToDict(chunk_metadata._pb, preserving_proto_field_name=True)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - best effort
            chunk_dict = {}
        if chunk_dict:
            candidate = _pull_from_dict(chunk_dict)
            if candidate:
                return candidate

    metadata = getattr(ctx, "metadata", None)
    if metadata is not None:
        if isinstance(metadata, dict):
            candidate = _pull_from_dict(metadata)
            if candidate:
                return candidate
        else:
            try:
                meta_dict = MessageToDict(metadata._pb, preserving_proto_field_name=True)  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - best effort
                meta_dict = {}
            if meta_dict:
                candidate = _pull_from_dict(meta_dict)
                if candidate:
                    return candidate
    return None


def _clean_snippet(snippet: Optional[str]) -> Optional[str]:
    if not snippet:
        return None
    collapsed = " ".join(snippet.split())
    max_len = 240
    if len(collapsed) > max_len:
        return collapsed[:max_len].rstrip() + "…"
    return collapsed


def _make_snippet_from_match(text: str, start: int, length: int, padding: int = 120) -> Optional[str]:
    begin = max(0, start - padding)
    end = min(len(text), start + length + padding)
    snippet = text[begin:end]
    return _clean_snippet(snippet)


def supplement_answer_evidence_from_contexts(
    answers: List[RagAnswer],
    contexts: List[object],
    *,
    max_matches: int = 3,
) -> None:
    if not answers or not contexts:
        return
    for answer in answers:
        if answer.evidence:
            continue
        raw_text = (answer.text or "").strip()
        if not raw_text:
            continue
        lowered = raw_text.lower()
        if lowered.startswith("no ") or lowered.startswith("not "):
            continue
        fragments = [segment.strip() for segment in raw_text.replace("\r", "").split("\n") if segment.strip()]
        if not fragments:
            fragments = [raw_text]
        seen_keys: Set[Tuple[str, Optional[str]]] = set()
        matches = 0
        for fragment in fragments:
            normalized_fragment = fragment.lower()
            if len(normalized_fragment) < 4:
                continue
            for ctx in contexts:
                ctx_text = getattr(ctx, "text", "") or ""
                if not ctx_text:
                    continue
                ctx_lower = ctx_text.lower()
                idx = ctx_lower.find(normalized_fragment)
                if idx == -1:
                    continue
                source_uri = getattr(ctx, "source_uri", "") or ""
                if not source_uri:
                    continue
                page_label = _extract_page_label(ctx)
                key = (source_uri, page_label)
                if key in seen_keys:
                    continue
                snippet = _make_snippet_from_match(ctx_text, idx, len(fragment))
                answer.evidence.append(
                    AnswerEvidence(
                        docId=source_uri,
                        docTitle=source_uri.split("/")[-1],
                        docUri=source_uri,
                        pageLabel=page_label,
                        snippet=snippet,
                        distance=None,
                    )
                )
                seen_keys.add(key)
                matches += 1
                if matches >= max_matches:
                    break
            if matches >= max_matches:
                break


def populate_answer_evidence(answers: List[RagAnswer], documents: List[RagDocument]) -> None:
    if not answers or not documents:
        for answer in answers:
            answer.evidence = []
        return

    doc_lookup: Dict[str, RagDocument] = {}
    for doc in documents:
        if doc.uri:
            doc_lookup.setdefault(doc.uri, doc)
        if doc.id:
            doc_lookup.setdefault(doc.id, doc)

    if not doc_lookup:
        for answer in answers:
            answer.evidence = []
        return

    for answer in answers:
        entries: List[AnswerEvidence] = []
        seen: set[Tuple[str, Optional[str]]] = set()
        for citation in answer.citations or []:
            for source in citation.sources or []:
                uri = source.get("sourceUri") or source.get("uri")
                if not uri:
                    continue
                doc = doc_lookup.get(uri)
                if not doc:
                    continue
                metadata = doc.metadata or {}
                page_label = None
                if isinstance(metadata, dict):
                    raw_page = metadata.get("pageLabel") or metadata.get("page") or metadata.get("page_number")
                    if raw_page is not None:
                        page_label = str(raw_page).strip() or None
                key = (uri, page_label)
                if key in seen:
                    continue
                seen.add(key)
                entries.append(
                    AnswerEvidence(
                        docId=doc.id,
                        docTitle=doc.title,
                        docUri=doc.uri,
                        pageLabel=page_label,
                        snippet=_clean_snippet(doc.snippet),
                        distance=float(metadata.get("distance")) if isinstance(metadata.get("distance"), (int, float)) else None,
                    )
                )
        answer.evidence = entries
