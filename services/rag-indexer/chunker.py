from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List


@dataclass
class Chunk:
    chunk_id: str
    tender_id: str
    text: str
    metadata: dict[str, Any]


def chunk_document(
    tender_id: str,
    document: dict[str, Any],
    *,
    max_chars: int = 1200,
) -> List[Chunk]:
    pages = document.get("pages", [])
    sections = document.get("sections", [])
    tables = document.get("tables", [])

    anchor_blocks = _build_anchor_block_lookup(pages)
    chunks: list[Chunk] = []

    for section in sections:
        section_id = section.get("sectionId") or "section"
        page_range = section.get("pageRange") or {}
        start_page = page_range.get("start") or page_range.get("page") or 1
        end_page = page_range.get("end") or start_page
        title = section.get("title") or "Untitled Section"

        blocks = _collect_blocks_in_range(anchor_blocks, start_page, end_page)
        if not blocks:
            continue

        paragraphs = [title] + blocks
        chunks.extend(
            _split_into_chunks(
                tender_id,
                section_id,
                paragraphs,
                max_chars=max_chars,
                base_metadata={
                    "sectionId": section_id,
                    "sectionTitle": title,
                    "pageRange": {"start": start_page, "end": end_page},
                },
            )
        )

    for table in tables:
        table_id = table.get("tableId") or "table"
        page = table.get("page")
        rows = _render_table(table)
        if rows:
            chunks.extend(
                _split_into_chunks(
                    tender_id,
                    f"table:{table_id}",
                    rows,
                    max_chars=max_chars,
                    base_metadata={
                        "tableId": table_id,
                        "page": page,
                    },
                )
            )

    # Fallback: capture remaining page blocks not covered by sections
    fallback_chunks = _collect_fallback_chunks(anchor_blocks, sections)
    chunks.extend(
        _split_into_chunks(
            tender_id,
            "page-block",
            fallback_chunks,
            max_chars=max_chars,
            base_metadata={"note": "fallback"},
        )
    )

    return [chunk for chunk in chunks if chunk.text.strip()]


def _build_anchor_block_lookup(pages: Iterable[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    page_map: dict[int, list[dict[str, Any]]] = {}
    for page in pages or []:
        page_number = page.get("pageNumber")
        if not page_number:
            continue
        blocks = page_map.setdefault(page_number, [])
        for block in page.get("blocks", []):
            if isinstance(block, dict):
                blocks.append(block)
    return page_map


def _collect_blocks_in_range(anchor_blocks: dict[int, list[dict[str, Any]]], start_page: int, end_page: int) -> list[str]:
    texts: list[str] = []
    for page_number in range(start_page, end_page + 1):
        for block in anchor_blocks.get(page_number, []):
            text = block.get("text")
            if text:
                texts.append(text)
    return texts


def _render_table(table: dict[str, Any]) -> list[str]:
    headers = table.get("headers", []) or []
    body_rows = table.get("rows", []) or []
    rendered: list[str] = []
    header_cells = [cell.get("text") for cell in headers]
    if any(header_cells):
        rendered.append(" | ".join(header_cells))
    for row in body_rows:
        cells = [cell.get("text") for cell in row]
        rendered.append(" | ".join(cells))
    return rendered


def _split_into_chunks(
    tender_id: str,
    prefix: str,
    paragraphs: list[str],
    *,
    max_chars: int,
    base_metadata: dict[str, Any],
) -> list[Chunk]:
    chunks: list[Chunk] = []
    buffer: list[str] = []
    current_len = 0
    counter = 0

    for paragraph in paragraphs:
        paragraph = (paragraph or "").strip()
        if not paragraph:
            continue
        if current_len + len(paragraph) > max_chars and buffer:
            text = "\n".join(buffer)
            chunk_id = f"{prefix}-{counter}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    tender_id=tender_id,
                    text=text,
                    metadata={**base_metadata, "sequence": counter},
                )
            )
            buffer = []
            current_len = 0
            counter += 1
        buffer.append(paragraph)
        current_len += len(paragraph)

    if buffer:
        chunk_id = f"{prefix}-{counter}"
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                tender_id=tender_id,
                text="\n".join(buffer),
                metadata={**base_metadata, "sequence": counter},
            )
        )

    return chunks


def _collect_fallback_chunks(anchor_blocks: dict[int, list[dict[str, Any]]], sections: Iterable[dict[str, Any]]) -> list[str]:
    covered_pages = set()
    for section in sections or []:
        page_range = section.get("pageRange") or {}
        start_page = page_range.get("start") or page_range.get("page")
        end_page = page_range.get("end") or start_page
        if start_page and end_page:
            covered_pages.update(range(start_page, end_page + 1))

    texts: list[str] = []
    for page_number, blocks in anchor_blocks.items():
        if page_number in covered_pages:
            continue
        for block in blocks:
            text = block.get("text")
            if text:
                texts.append(f"[Page {page_number}] {text}")
    return texts
