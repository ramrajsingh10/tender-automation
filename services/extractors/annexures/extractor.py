from __future__ import annotations

from typing import Any, Dict, List


def extract_annexures(normalized_document: dict[str, Any]) -> list[dict[str, Any]]:
    attachments = normalized_document.get("document", {}).get("attachments", [])
    anchors_index: Dict[str, Dict[str, int]] = (
        normalized_document.get("textIndex", {}).get("anchors", {}) or {}
    )
    results: list[dict[str, Any]] = []

    for attachment in attachments:
        anchor_id = attachment.get("anchor")
        provenance_anchor = anchors_index.get(anchor_id or "", {})
        results.append(
            {
                "factType": "annexure.reference",
                "payload": {
                    "name": attachment.get("name"),
                    "sectionId": attachment.get("sectionId"),
                    "pageRange": attachment.get("pageRange"),
                    "rawUri": attachment.get("rawUri"),
                },
                "confidence": 0.8,
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
