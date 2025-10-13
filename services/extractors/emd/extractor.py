from __future__ import annotations

import re
from typing import Any, Dict, List

from dateutil import parser

CURRENCY_PATTERN = re.compile(
    r"(INR|₹|\$|USD|EUR|£|Rs\.?)\s?([\d,]+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)


EMD_KEYWORDS = [
    "earnest money deposit",
    "emd",
    "bid security",
    "bid bond",
]


def extract_emd(normalized_document: dict[str, Any]) -> list[dict[str, Any]]:
    pages = normalized_document.get("document", {}).get("pages", [])
    anchors_index: Dict[str, Dict[str, int]] = (
        normalized_document.get("textIndex", {}).get("anchors", {}) or {}
    )
    results: list[dict[str, Any]] = []

    for page in pages:
        for block in page.get("blocks", []):
            text = (block.get("text") or "").strip()
            if not text:
                continue
            lowered = text.lower()
            anchor_id = block.get("anchorId")

            if any(keyword in lowered for keyword in EMD_KEYWORDS):
                currency_match = CURRENCY_PATTERN.search(text)
                amount_text = currency_match.group(0) if currency_match else None

                due_date = None
                for sentence in re.split(r"[.;]\s*", text):
                    if "before" in sentence or "latest" in sentence:
                        maybe_date = _extract_date(sentence)
                        if maybe_date:
                            due_date = maybe_date
                            break

                provenance_anchor = anchors_index.get(anchor_id or "", {})
                results.append(
                    {
                        "factType": "financial.emd",
                        "payload": {
                            "amountText": amount_text,
                            "currency": currency_match.group(1) if currency_match else None,
                            "amountNumeric": _normalize_amount(currency_match.group(2)) if currency_match else None,
                            "dueAt": due_date.isoformat() if due_date else None,
                            "rawText": text,
                        },
                        "confidence": 0.6 if amount_text else 0.4,
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


def _normalize_amount(value: str | None) -> float | None:
    if not value:
        return None
    sanitized = value.replace(",", "")
    try:
        return float(sanitized)
    except ValueError:
        return None


def _extract_date(text: str):
    try:
        return parser.parse(text, fuzzy=True)
    except (parser.ParserError, ValueError):
        return None
