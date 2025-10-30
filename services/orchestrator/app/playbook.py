from __future__ import annotations

import json
from datetime import datetime, timezone
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from google.cloud import storage

from .clients import get_storage_client
from .config import settings
from .generative import generate_document_answer, has_substantive_answer
from .models import (
    PlaybookQuestion,
    RagAnswer,
    RagPlaybookRequest,
    RagPlaybookResponse,
    RagPlaybookResult,
    RagQueryRequest,
    RagQueryResponse,
)
from .rag import execute_vertex_search, import_rag_files, map_rag_files_by_uri

_DEFAULT_CONFIG: Sequence[Dict[str, object]] = [
    {
        "id": "document_id",
        "display": "Extract the document identifier exactly as stated.",
        "prompt": (
            "Extract the document identifier (tender ID / RFP ID / reference number / RFP No.) exactly as stated in the tender pack. "
            "Ignore placeholder or blank lines that contain only underscores or tokens such as NA, N.A., or Not Available. "
            "Return the answer as a JSON array of objects with fields 'label' and 'value' capturing the filled-in identifier."
        ),
        "pageSize": 4,
    },
    {
        "id": "submission_deadlines",
        "display": "List submission deadlines with dates and times.",
        "prompt": (
            "List every submission related deadline with date and time. Include the schedule label (for example 'Last Date for Submission') and the precise date/time exactly as written. "
            "Skip rows that do not contain an actual date or time or that are left blank. "
            "Return the answer as a JSON array of objects with fields 'label' and 'value'."
        ),
        "pageSize": 10,
    },
]


def _playbook_config_path() -> Path:
    if settings.playbook_config_path:
        return Path(settings.playbook_config_path)
    return Path(__file__).resolve().parent.parent / "config" / "playbook_questions.json"


@lru_cache()
def _load_playbook_config() -> Sequence[Dict[str, object]]:
    path = _playbook_config_path()
    try:
        with path.open(encoding="utf-8") as fp:
            return json.load(fp)
    except FileNotFoundError:
        return _DEFAULT_CONFIG
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid playbook configuration JSON: {path}: {exc}") from exc


def resolve_playbook_questions(questions: List[PlaybookQuestion] | None) -> List[PlaybookQuestion]:
    if questions:
        return questions
    definitions = _load_playbook_config()
    return [PlaybookQuestion(**item) for item in definitions]


def run_playbook(request: RagPlaybookRequest) -> RagPlaybookResponse:
    questions = resolve_playbook_questions(request.questions)
    rag_file_mapping: Dict[str, str] = {}
    rag_file_names: List[str] = []

    if request.ragFileIds:
        rag_file_names = list(request.ragFileIds)
    elif request.gcsUris:
        rag_file_mapping = import_rag_files(request.gcsUris)
        rag_file_names = list(rag_file_mapping.values())
    else:
        raise RuntimeError("No ragFileIds or gcsUris provided for playbook execution.")

    rag_file_ids_for_query = rag_file_names or None
    results: List[RagPlaybookResult] = []
    retrieval_cache: Dict[Tuple[str, str], RagQueryResponse] = {}

    for question in questions:
        query_page_size = question.page_size or request.pageSize
        source_uris = list(request.gcsUris) if request.gcsUris else list(rag_file_mapping.keys())
        if not source_uris and request.ragFileIds:
            mapping = map_rag_files_by_uri()
            wanted = set(request.ragFileIds)
            source_uris = [uri for uri, name in mapping.items() if name in wanted]

        cache_key = (question.id, question.prompt.strip())
        if cache_key in retrieval_cache:
            query_response = retrieval_cache[cache_key]
        else:
            query_response = execute_vertex_search(
                RagQueryRequest(
                    tenderId=request.tenderId,
                    question=question.prompt,
                    pageSize=query_page_size,
                    gcsUris=source_uris,
                    ragFileIds=rag_file_ids_for_query,
                )
            )
            retrieval_cache[cache_key] = query_response
        rag_answers = query_response.answers or []
        structured_entries, raw_text = generate_document_answer(
            question.prompt,
            source_uris,
            mode="structured",
        )
        filtered_entries = filter_structured_entries(question.id, structured_entries)

        answers: List[RagAnswer]
        if filtered_entries:
            formatted_text = format_structured_entries(filtered_entries)
            citation_list = rag_answers[0].citations if rag_answers else []
            answers = [
                RagAnswer(
                    text=formatted_text,
                    citations=citation_list,
                )
            ]
        elif has_substantive_answer(rag_answers):
            answers = rag_answers
        elif raw_text:
            cleaned_text = raw_text.strip().strip("`").strip()
            answers = [
                RagAnswer(
                    text=cleaned_text or "No relevant context found.",
                    citations=rag_answers[0].citations if rag_answers else [],
                )
            ]
        else:
            answers = [RagAnswer(text="No relevant context found.", citations=[])]

        results.append(
            RagPlaybookResult(
                questionId=question.id,
                question=question.display,
                answers=answers,
                documents=query_response.documents,
            )
        )

    payload = {
        "tenderId": request.tenderId,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "results": [result.model_dump(mode="json") for result in results],
    }
    output_uri = write_results_to_gcs(request.tenderId, payload)

    if rag_file_mapping:
        rag_file_handles = [
            {"ragFileName": name, "sourceUri": uri}
            for uri, name in rag_file_mapping.items()
]
    elif request.ragFileIds:
        rag_file_handles = [{"ragFileName": name, "sourceUri": None} for name in request.ragFileIds]
    else:
        rag_file_handles = []

    return RagPlaybookResponse(results=results, outputUri=output_uri, ragFiles=rag_file_handles)


def write_results_to_gcs(tender_id: str, payload: Dict[str, object]) -> str:
    client: storage.Client = get_storage_client()
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


def filter_structured_entries(question_id: str, entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    filtered: List[Dict[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for entry in entries:
        label = str(entry.get("label", "") or "").strip()
        value = str(entry.get("value", "") or "").strip()
        if not value:
            continue
        if "__" in value or value.replace("_", "").strip() == "":
            continue
        if question_id == "document_id":
            if not any(char.isalnum() for char in value):
                continue
        if question_id == "submission_deadlines":
            if not _looks_like_schedule(value):
                continue
        key = (label.lower(), value.lower())
        if key in seen:
            continue
        seen.add(key)
        filtered.append({"label": label, "value": value})
    return filtered


def format_structured_entries(entries: List[Dict[str, str]]) -> str:
    lines: List[str] = []
    for entry in entries:
        label = entry.get("label", "").strip()
        value = entry.get("value", "").strip()
        if label and value:
            lines.append(f"{label}: {value}")
        else:
            lines.append(value or label)
    return "\n".join(lines)


MONTH_TOKENS = {
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
}

DATE_REGEXPS = [
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    re.compile(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b"),
]

TIME_REGEX = re.compile(r"\b\d{1,2}:\d{2}\b")


def _looks_like_schedule(value: str) -> bool:
    normalized = value.lower()
    if any(month in normalized for month in MONTH_TOKENS):
        return True
    if TIME_REGEX.search(normalized):
        return True
    if any(regex.search(value) for regex in DATE_REGEXPS):
        return True
    digits = sum(char.isdigit() for char in value)
    return digits >= 4
