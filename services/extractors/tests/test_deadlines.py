from __future__ import annotations

from services.extractors.deadlines.extractor import extract_deadlines
from services.extractors.emd.extractor import extract_emd
from services.extractors.requirements.extractor import extract_requirements
from services.extractors.penalties.extractor import extract_penalties
from services.extractors.annexures.extractor import extract_annexures


def test_extract_deadlines_finds_submission_and_prebid():
    normalized = {
        "document": {
            "pages": [
                {
                    "pageNumber": 1,
                    "blocks": [
                        {
                            "anchorId": "a001_0001",
                            "text": "Bid submission deadline is 31 March 2024 at 5 PM.",
                        },
                        {
                            "anchorId": "a001_0002",
                            "text": "Pre-bid meeting scheduled for 15 March 2024.",
                        },
                    ],
                }
            ]
        },
        "textIndex": {
            "anchors": {
                "a001_0001": {"page": 1, "startIndex": 0, "endIndex": 52},
                "a001_0002": {"page": 1, "startIndex": 53, "endIndex": 94},
            }
        },
    }

    facts = extract_deadlines(normalized)
    fact_types = {fact["factType"] for fact in facts}
    assert "deadline.submission" in fact_types
    assert "deadline.prebid" in fact_types


def test_extract_emd_amount_and_due_date():
    normalized = {
        "document": {
            "pages": [
                {
                    "pageNumber": 2,
                    "blocks": [
                        {
                            "anchorId": "a002_0001",
                            "text": "Earnest Money Deposit (EMD) of INR 50,000 must be submitted before 20 April 2024.",
                        }
                    ],
                }
            ]
        },
        "textIndex": {"anchors": {"a002_0001": {"page": 2, "startIndex": 0, "endIndex": 96}}},
    }

    facts = extract_emd(normalized)
    assert facts
    payload = facts[0]["payload"]
    assert payload["amountNumeric"] == 50000.0
    assert payload["dueAt"] is not None


def test_extract_requirements_section():
    normalized = {
        "document": {
            "sections": [
                {
                    "sectionId": "sec-1",
                    "title": "Technical Requirements",
                    "anchor": "sec-anchor",
                    "pageRange": {"start": 10, "end": 12},
                }
            ]
        },
        "textIndex": {"anchors": {"sec-anchor": {"page": 10, "startIndex": 0, "endIndex": 20}}},
    }

    facts = extract_requirements(normalized)
    assert facts
    assert facts[0]["factType"] == "technical.requirements"


def test_extract_penalties_from_table_and_block():
    normalized = {
        "document": {
            "tables": [
                {
                    "tableId": "tbl-penalty",
                    "headers": [{"text": "Penalty"}],
                    "rows": [
                        [
                            {"anchorId": "pen-1", "text": "Delay",},
                            {"text": "1% per week"},
                        ]
                    ],
                }
            ],
            "pages": [
                {
                    "pageNumber": 5,
                    "blocks": [
                        {
                            "anchorId": "pen-2",
                            "text": "Liquidated damages shall apply.",
                        }
                    ],
                }
            ],
        },
        "textIndex": {
            "anchors": {
                "pen-1": {"page": 4, "startIndex": 0, "endIndex": 4},
                "pen-2": {"page": 5, "startIndex": 0, "endIndex": 32},
            }
        },
    }

    facts = extract_penalties(normalized)
    fact_types = {fact["factType"] for fact in facts}
    assert "penalties.table" in fact_types
    assert "penalties.block" in fact_types


def test_extract_annexures_from_attachments():
    normalized = {
        "document": {
            "attachments": [
                {
                    "name": "Annexure A",
                    "sectionId": "sec-annex",
                    "pageRange": {"start": 20, "end": 25},
                    "rawUri": "gs://bucket/annexure-a.pdf",
                    "anchor": "annex-anchor",
                }
            ]
        },
        "textIndex": {"anchors": {"annex-anchor": {"page": 20, "startIndex": 0, "endIndex": 10}}},
    }

    annexures = extract_annexures(normalized)
    assert annexures
    payload = annexures[0]["payload"]
    assert payload["name"] == "Annexure A"
