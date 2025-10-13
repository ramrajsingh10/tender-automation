from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


class NormalizationError(RuntimeError):
    """Raised when Document AI output cannot be normalized."""


@dataclass(frozen=True)
class PageContext:
    page_index: int
    text: str


def normalize_docai_documents(
    documents: Iterable[dict[str, Any]],
    *,
    tender_id: str,
    raw_uris: list[str],
    docai_output_uris: list[str],
    created_at: datetime | None = None,
) -> dict[str, Any]:
    docs = list(documents)
    if not docs:
        raise NormalizationError("No Document AI documents supplied for normalization.")

    timestamp = (created_at or datetime.now(timezone.utc)).isoformat()
    anchors: dict[str, dict[str, int]] = {}
    pages_payload: list[dict[str, Any]] = []
    tables_payload: list[dict[str, Any]] = []
    sections_payload: list[dict[str, Any]] = []
    attachments_payload: list[dict[str, Any]] = []

    for doc_idx, document in enumerate(docs):
        text = document.get("text", "")
        pages = document.get("pages", [])
        page_offset = len(pages_payload)

        for local_index, page in enumerate(pages):
            page_number = page.get("pageNumber") or (page_offset + local_index + 1)
            page_context = PageContext(page_index=page_number, text=text)
            page_payload = _build_page_payload(page, page_context, anchors)
            pages_payload.append(page_payload)
            tables_payload.extend(
                _build_table_payload(page, page_context, anchors, doc_idx)
            )
        section_result = _build_sections(document, anchors)
        sections_payload.extend(section_result["sections"])
        attachments_payload.extend(section_result["attachments"])

    metadata = {
        "ocrApplied": True,
        "docAiRevisionCount": len(docs[0].get("revisions", [])),
        "processorVersion": docs[0]
        .get("processorId", "")
        .split("/")[-1]
        if docs[0].get("processorId")
        else None,
    }

    return {
        "tenderId": tender_id,
        "schemaVersion": 1,
        "source": {
            "docAiOutput": docai_output_uris,
            "rawBundle": raw_uris,
        },
        "document": {
            "pages": pages_payload,
            "sections": sections_payload,
            "tables": tables_payload,
            "attachments": attachments_payload,
        },
        "textIndex": {"anchors": anchors},
        "metadata": metadata,
        "createdAt": timestamp,
    }


def _build_page_payload(
    page: dict[str, Any],
    page_context: PageContext,
    anchors: dict[str, dict[str, int]],
) -> dict[str, Any]:
    dimension = page.get("dimension", {})
    blocks: list[dict[str, Any]] = []
    block_counter = 0

    for paragraph in page.get("paragraphs", []):
        anchor_id = _generate_anchor_id(page_context.page_index, block_counter)
        text = _resolve_text(paragraph.get("layout", {}), page_context.text)
        anchors[anchor_id] = _anchor_record(paragraph.get("layout", {}), page_context.page_index)
        blocks.append(
            {
                "type": "text",
                "anchorId": anchor_id,
                "boundingPoly": _normalize_vertices(paragraph.get("layout", {})),
                "text": text,
            }
        )
        block_counter += 1

    for block in page.get("blocks", []):
        anchor_id = _generate_anchor_id(page_context.page_index, block_counter)
        text = _resolve_text(block.get("layout", {}), page_context.text)
        anchors[anchor_id] = _anchor_record(block.get("layout", {}), page_context.page_index)
        blocks.append(
            {
                "type": "block",
                "anchorId": anchor_id,
                "boundingPoly": _normalize_vertices(block.get("layout", {})),
                "text": text,
            }
        )
        block_counter += 1

    return {
        "pageNumber": page_context.page_index,
        "dimensions": {
            "width": dimension.get("width"),
            "height": dimension.get("height"),
            "unit": dimension.get("unit"),
        },
        "blocks": blocks,
    }


def _build_table_payload(
    page: dict[str, Any],
    page_context: PageContext,
    anchors: dict[str, dict[str, int]],
    doc_index: int,
) -> list[dict[str, Any]]:
    tables_payload: list[dict[str, Any]] = []
    for table_index, table in enumerate(page.get("tables", [])):
        header_cells = table.get("headerRows", [])
        body_rows = table.get("bodyRows", [])
        table_id = f"tbl-{doc_index}-{page_context.page_index}-{table_index}"

        headers = [
            {
                "anchorId": _capture_cell_anchor(
                    cell, page_context, anchors, f"{table_id}-h{idx}"
                ),
                "text": _resolve_text(cell.get("layout", {}), page_context.text),
            }
            for idx, cell in enumerate(header_cells[0]["cells"])
        ] if header_cells else []

        rows = []
        for row_idx, row in enumerate(body_rows):
            row_cells = []
            for col_idx, cell in enumerate(row.get("cells", [])):
                cell_anchor_id = _capture_cell_anchor(
                    cell,
                    page_context,
                    anchors,
                    f"{table_id}-r{row_idx}c{col_idx}",
                )
                row_cells.append(
                    {
                        "anchorId": cell_anchor_id,
                        "text": _resolve_text(cell.get("layout", {}), page_context.text),
                    }
                )
            rows.append(row_cells)

        tables_payload.append(
            {
                "tableId": table_id,
                "page": page_context.page_index,
                "headers": headers,
                "rows": rows,
            }
        )
    return tables_payload


def _build_sections(document: dict[str, Any], anchors: dict[str, dict[str, int]]) -> dict[str, Any]:
    sections = []
    attachments = []
    for entity in document.get("entities", []):
        entity_type = (entity.get("type") or "").lower()
        is_annexure = "annexure" in entity_type
        if "section" not in entity_type and not is_annexure:
            continue
        text_anchor = entity.get("textAnchor", {})
        page_anchor = entity.get("pageAnchor", {})
        anchor_id = entity.get("id") or _generate_entity_anchor(entity, anchors)
        if text_anchor:
            anchors.setdefault(
                anchor_id,
                _anchor_record_from_text_anchor(text_anchor, page_anchor),
            )
        section_payload = {
            "sectionId": anchor_id,
            "title": entity.get("mentionText"),
            "type": entity_type,
            "pageRange": _page_range_from_anchor(page_anchor, text_anchor),
            "anchor": anchor_id,
        }
        sections.append(section_payload)

        if is_annexure:
            attachments.append(
                {
                    "name": entity.get("mentionText"),
                    "sectionId": anchor_id,
                    "pageRange": section_payload["pageRange"],
                    "rawUri": entity.get("fileUri"),
                    "anchor": anchor_id,
                }
            )
    return {"sections": sections, "attachments": attachments}


def _generate_anchor_id(page_number: int, block_index: int) -> str:
    return f"a{page_number:03d}_{block_index:04d}"


def _normalize_vertices(layout: dict[str, Any]) -> list[dict[str, float]]:
    poly = (layout or {}).get("boundingPoly", {})
    vertices = poly.get("normalizedVertices", [])
    return [{"x": v.get("x"), "y": v.get("y")} for v in vertices]


def _resolve_text(layout: dict[str, Any], full_text: str) -> str:
    text_anchor = (layout or {}).get("textAnchor", {})
    return _text_from_anchor(text_anchor, full_text)


def _text_from_anchor(anchor: dict[str, Any], full_text: str) -> str:
    segments = anchor.get("textSegments", [])
    fragments = []
    for segment in segments:
        start = int(segment.get("startIndex", 0))
        end = int(segment.get("endIndex", 0))
        fragments.append(full_text[start:end])
    return "".join(fragments).strip()


def _anchor_record(layout: dict[str, Any], page_number: int) -> dict[str, int]:
    text_anchor = (layout or {}).get("textAnchor", {})
    segments = text_anchor.get("textSegments", [])
    if not segments:
        return {"page": page_number}
    first = segments[0]
    last = segments[-1]
    return {
        "page": page_number,
        "startIndex": int(first.get("startIndex", 0)),
        "endIndex": int(last.get("endIndex", 0)),
    }


def _capture_cell_anchor(
    cell: dict[str, Any],
    page_context: PageContext,
    anchors: dict[str, dict[str, int]],
    anchor_id: str,
) -> str:
    anchors[anchor_id] = _anchor_record(cell.get("layout", {}), page_context.page_index)
    return anchor_id


def _page_range_from_anchor(page_anchor: dict[str, Any], text_anchor: dict[str, Any]) -> dict[str, int] | None:
    if page_anchor.get("pageRefs"):
        refs = page_anchor.get("pageRefs")
        pages = [ref.get("page") for ref in refs if "page" in ref]
        if pages:
            return {"start": min(pages), "end": max(pages)}
    segments = text_anchor.get("textSegments", [])
    if segments:
        start_page = page_anchor.get("pageRefs", [{}])[0].get("page", 1)
        return {"start": start_page, "end": start_page}
    return None


def _anchor_record_from_text_anchor(text_anchor: dict[str, Any], page_anchor: dict[str, Any]) -> dict[str, int]:
    segments = text_anchor.get("textSegments", [])
    if not segments:
        page = page_anchor.get("pageRefs", [{}])[0].get("page", 1)
        return {"page": page}
    first = segments[0]
    last = segments[-1]
    page = page_anchor.get("pageRefs", [{}])[0].get("page", 1)
    return {
        "page": page,
        "startIndex": int(first.get("startIndex", 0)),
        "endIndex": int(last.get("endIndex", 0)),
    }


def _generate_entity_anchor(entity: dict[str, Any], anchors: dict[str, dict[str, int]]) -> str:
    base = "section"
    counter = 0
    anchor_id = f"{base}-{counter}"
    while anchor_id in anchors:
        counter += 1
        anchor_id = f"{base}-{counter}"
    return anchor_id
