from __future__ import annotations

import json
import logging
import os
import re
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from vertexai.preview.generative_models import GenerativeModel, GenerationConfig, Part
from google.auth import default as google_auth_default

from .clients import ensure_vertexai_initialized
from .config import settings

if TYPE_CHECKING:  # pragma: no cover - typing support
    from .models import RagAnswer

logger = logging.getLogger(__name__)


def run_generative_agent(
    project_id: str,
    location: str,
    question: str,
    contexts: List[object],
) -> Tuple[str, Optional[str]]:
    ensure_vertexai_initialized(project_id, location)
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
        matched_source = getattr(contexts[0], "source_uri", None) if contexts else None
    return answer_text, matched_source


def generate_document_answer(
    question: str,
    gcs_uris: List[str],
    *,
    mode: str = "structured",
) -> Tuple[List[Dict[str, str]], str]:
    if not gcs_uris:
        return [], ""
    project_id = settings.project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
    if not project_id:
        try:
            credentials, detected_project = google_auth_default()
            project_id = detected_project
        except Exception:  # pragma: no cover - metadata failures
            project_id = None
    location = settings.vertex_rag_location or _extract_location_from_path(settings.vertex_rag_corpus_path)
    if not project_id or not location:
        logger.warning(
            "Skipping direct document answer generation due to missing project (%s) or location (%s).",
            project_id,
            location,
        )
        return [], ""

    ensure_vertexai_initialized(project_id, location)
    model_id = settings.vertex_rag_generative_model or "gemini-2.5-flash"
    model = GenerativeModel(model_id)

    parts: List[Part] = [Part.from_uri(uri, mime_type=_guess_mime_type(uri)) for uri in gcs_uris]
    if mode == "structured":
        instruction = (
            "You are assisting with tender reviews. Use the supplied tender documents to answer the question by quoting "
            "the exact wording from the text. Return the answer as a JSON array of objects, each with fields 'label' and "
            "'value', preserving numbering, punctuation, dates, and times exactly as written. Use concise labels drawn from "
            "the document (for example, table headers). Ignore lines that contain only underscores or placeholder tokens such as NA, N.A., or Not Available. "
            "If the documents do not contain the requested information, respond with NOT_FOUND. "
            "Example output: [{\"label\": \"RFP Number\", \"value\": \"RFP No. 001/MPSAPS/2025\"}]."
        )
    else:
        instruction = (
            "You are assisting with tender reviews. Answer the question using the supplied tender documents. "
            "Quote or summarise the relevant information exactly as written, including numbering or bullet labels when helpful. "
            "Respond with plain text (one or two sentences). If the documents do not contain the requested information, respond with NOT_FOUND."
        )
    try:
        response = model.generate_content(
            parts + [Part.from_text(f"{instruction}\n\nQuestion:\n{question}")],
            generation_config=GenerationConfig(temperature=0.0, max_output_tokens=1024),
        )
        answer_text = (getattr(response, "text", "") or "").strip()
    except Exception as exc:  # pragma: no cover - generative call can raise
        logger.warning("Direct document analysis failed: %s", exc)
        return [], ""

    clean_text = _strip_code_fence(answer_text)
    if not clean_text or clean_text.upper().startswith("NOT_FOUND"):
        return [], ""

    if mode == "structured":
        try:
            structured = json.loads(clean_text)
        except json.JSONDecodeError:
            recovered = _recover_pairs_from_fallback(clean_text)
            if recovered:
                return recovered, clean_text
            return [], clean_text

        if not isinstance(structured, list):
            return [], clean_text

        normalized: List[Dict[str, str]] = []
        for entry in structured:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label", "") or "").strip()
            value = str(entry.get("value", "") or "").strip()
            normalized.append({"label": label, "value": value})
        return normalized, clean_text

    return [], clean_text


def has_substantive_answer(answers: List["RagAnswer"]) -> bool:
    for answer in answers:
        raw_text = (answer.text or "").strip()
        if not raw_text:
            continue
        lowered = raw_text.lower()
        if lowered == "no relevant context found.":
            continue
        if "__" in raw_text:
            continue
        digit_count = sum(char.isdigit() for char in raw_text)
        if digit_count == 1 and "0" in raw_text and len(raw_text) < 40:
            continue
        if digit_count >= 2:
            return True
        if digit_count == 0:
            tokens = [token for token in lowered.replace("\n", " ").split() if token]
            if tokens and not all(token in {"rfp", "no.", "no", "number", "identifier", "id", "tender", "reference"} for token in tokens):
                return True
            continue
        return True
    return False


def _guess_mime_type(uri: str) -> str:
    if uri.endswith(".pdf"):
        return "application/pdf"
    if uri.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"


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


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
    if stripped.endswith("```"):
        stripped = stripped[:-3].rstrip()
    return stripped


def _recover_pairs_from_fallback(text: str) -> List[Dict[str, str]]:
    pairs: List[Dict[str, str]] = []
    label: Optional[str] = None
    value: Optional[str] = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        label_match = re.search(r'"label"\s*:\s*"([^"\n]+)', line)
        if label_match:
            if label and value:
                pairs.append({"label": label, "value": value})
            label = label_match.group(1).strip()
            value = None
            continue
        value_match = re.search(r'"value"\s*:\s*"([^"\n]+)', line)
        if value_match:
            value = value_match.group(1).strip()
            if label:
                pairs.append({"label": label, "value": value})
                label = None
                value = None
            continue
    if label and value:
        pairs.append({"label": label, "value": value})
    return pairs
