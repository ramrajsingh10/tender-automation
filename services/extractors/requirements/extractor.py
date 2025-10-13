from __future__ import annotations

import re
from typing import Any, Dict

REQUIREMENT_SECTION_PATTERN = re.compile(r"(technical|financial) requirements", re.IGNORECASE)


def extract_requirements(normalized_document: dict[str, Any]) -> list[dict[str, Any]]:
    sections = normalized_document.get("document", {}).get("sections", [])
    anchors_index: Dict[str, Dict[str, int]] = (
        normalized_document.get("textIndex", {}).get("anchors", {}) or {}
    )
    results: list[dict[str, Any]] = []

    for section in sections:
        title = section.get("title", "")
        if not title or not REQUIREMENT_SECTION_PATTERN.search(title):
            continue

        section_type = "technical" if "technical" in title.lower() else "financial"
        anchor_id = section.get("anchor")
        page_range = section.get("pageRange")
        provenance_anchor = anchors_index.get(anchor_id or "", {})

        results.append(
            {
                "factType": f"{section_type}.requirements",
                "payload": {
                    "title": title,
                    "sectionId": section.get("sectionId"),
                    "pageRange": page_range,
                },
                "confidence": 0.5,
                "provenance": {
                    "textAnchors": [
                        {
                            "anchorId": anchor_id,
                            **provenance_anchor,
                        }
                    ]
                    if anchor_id
                    else []
                },
            }
        )

    return results
