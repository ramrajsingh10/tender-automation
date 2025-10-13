from __future__ import annotations

import re
from typing import Any, Dict

PENALTY_PATTERN = re.compile(
    r"(penalty|liquidated damages|ld)\b", re.IGNORECASE
)


def extract_penalties(normalized_document: dict[str, Any]) -> list[dict[str, Any]]:
    tables = normalized_document.get("document", {}).get("tables", [])
    pages = normalized_document.get("document", {}).get("pages", [])
    anchors_index: Dict[str, Dict[str, int]] = (
        normalized_document.get("textIndex", {}).get("anchors", {}) or {}
    )
    results: list[dict[str, Any]] = []

    for table in tables:
        headers = [cell.get("text", "").lower() for cell in table.get("headers", [])]
        if any(PENALTY_PATTERN.search(header) for header in headers):
            for row in table.get("rows", []):
                row_text = " | ".join(cell.get("text", "") for cell in row)
                anchor_id = row[0].get("anchorId") if row else None
                provenance_anchor = anchors_index.get(anchor_id or "", {})
                results.append(
                    {
                        "factType": "penalties.table",
                        "payload": {"rowText": row_text, "tableId": table.get("tableId")},
                        "confidence": 0.5,
                        "provenance": {
                            "textAnchors": [
                                {"anchorId": anchor_id, **provenance_anchor}
                            ]
                            if anchor_id
                            else []
                        },
                    }
                )

    for page in pages:
        for block in page.get("blocks", []):
            text = block.get("text", "")
            if PENALTY_PATTERN.search(text):
                anchor_id = block.get("anchorId")
                provenance_anchor = anchors_index.get(anchor_id or "", {})
                results.append(
                    {
                        "factType": "penalties.block",
                        "payload": {"text": text, "page": page.get("pageNumber")},
                        "confidence": 0.4,
                        "provenance": {
                            "textAnchors": [
                                {"anchorId": anchor_id, **provenance_anchor}
                            ]
                            if anchor_id
                            else []
                        },
                    }
                )

    return results
