from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Tuple

from dateutil import parser

DATE_PATTERN = re.compile(
    r"(\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})"
    r"|(\d{1,2}/\d{1,2}/\d{2,4})"
    r"|(\d{1,2}-\d{1,2}-\d{2,4})",
    re.IGNORECASE,
)


KEYWORD_TYPE_MAP: List[Tuple[str, str, str]] = [
    ("pre-bid", "deadline.prebid", "Pre-bid Meeting"),
    ("clarification", "deadline.clarification", "Clarifications Due"),
    ("submission", "deadline.submission", "Bid Submission Deadline"),
    ("bid opening", "deadline.bidopening", "Bid Opening"),
]


@dataclass
class ExtractedFact:
    fact_type: str
    title: str
    due_at: str
    confidence: float
    anchor_id: str | None


def extract_deadlines(normalized_document: dict[str, Any]) -> list[dict[str, Any]]:
    pages = normalized_document.get("document", {}).get("pages", [])
    anchors_index: Dict[str, Dict[str, int]] = (
        normalized_document.get("textIndex", {}).get("anchors", {}) or {}
    )
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for page in pages:
        for block in page.get("blocks", []):
            text = (block.get("text") or "").strip()
            if not text:
                continue
            anchor_id = block.get("anchorId")
            matches = DATE_PATTERN.finditer(text)
            first_match = next(matches, None)
            if not first_match:
                continue
            date_text = first_match.group(0)
            parsed_date = _parse_date(date_text)
            if not parsed_date:
                continue

            fact_type, title, confidence = _classify_deadline(text)
            key = (fact_type, parsed_date.isoformat())
            if key in seen:
                continue
            seen.add(key)

            provenance_anchor = anchors_index.get(anchor_id or "", {})
            provenance = {
                "textAnchors": [
                    {
                        "anchorId": anchor_id,
                        **provenance_anchor,
                    }
                ]
                if anchor_id
                else []
            }

            results.append(
                {
                    "factType": fact_type,
                    "payload": {
                        "title": title,
                        "dueAt": parsed_date.isoformat(),
                        "timeZone": None,
                        "rawText": text,
                    },
                    "confidence": confidence,
                    "provenance": provenance,
                }
            )

    return results


def _parse_date(value: str) -> datetime | None:
    try:
        parsed = parser.parse(value, dayfirst=False, fuzzy=True)
        return parsed
    except (ValueError, parser.ParserError):
        return None


def _classify_deadline(text: str) -> tuple[str, str, float]:
    lowered = text.lower()
    for keyword, fact_type, title in KEYWORD_TYPE_MAP:
        if keyword in lowered:
            confidence = 0.7
            if "must" in lowered or "shall" in lowered:
                confidence += 0.1
            return fact_type, title, min(confidence, 0.95)
    return "deadline.other", "Important Deadline", 0.5
