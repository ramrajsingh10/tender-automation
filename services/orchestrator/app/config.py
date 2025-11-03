from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _load_service_map() -> dict[str, str]:
    """Compile service endpoint overrides from environment variables."""
    base_map: dict[str, str] = {}
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
    vertex_rag_default_top_k: int = int(os.getenv("VERTEX_RAG_SIMILARITY_TOP_K", "10"))
    raw_bucket: str = os.getenv("RAW_TENDER_BUCKET", "rawtenderdata")
    parsed_bucket: str = os.getenv("PARSED_TENDER_BUCKET", "parsedtenderdata")
    playbook_config_path: str = os.getenv("PLAYBOOK_CONFIG_PATH", "")
    vertex_rag_chunk_size_tokens: int = int(os.getenv("VERTEX_RAG_CHUNK_SIZE_TOKENS", "0"))
    vertex_rag_chunk_overlap_tokens: int = int(os.getenv("VERTEX_RAG_CHUNK_OVERLAP_TOKENS", "0"))
    vertex_rag_cache_ttl_seconds: int = int(os.getenv("VERTEX_RAG_CACHE_TTL_SECONDS", "300"))
    vertex_rag_cache_max_entries: int = int(os.getenv("VERTEX_RAG_CACHE_MAX_ENTRIES", "64"))
    vertex_rag_playbook_pacing_seconds: float = float(os.getenv("VERTEX_RAG_PLAYBOOK_PACING_SECONDS", "0"))


settings = Settings(service_map=_load_service_map())
