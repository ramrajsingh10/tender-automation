from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.ingest_api.main import _extract_tender_id, _parse_gcs_uri
from services.ingest_api.normalizer import NormalizationError, normalize_docai_documents


def test_extract_tender_id():
    assert _extract_tender_id("tid-123/docai/output/result-0.json") == "tid-123"
    assert _extract_tender_id("tid/docai/output/subdir/file.json") == "tid"
    assert _extract_tender_id("invalid/path.json") is None


def test_parse_gcs_uri():
    bucket, path = _parse_gcs_uri("gs://bucket-name/path/to/object.json")
    assert bucket == "bucket-name"
    assert path == "path/to/object.json"

    with pytest.raises(NormalizationError):
        _parse_gcs_uri("https://example.com/file")


def test_normalize_docai_documents_basic():
    document = {
        "text": "Section Header\nRow Header\nValue 1\nValue 2\nAnnexure A – Sample\n",
        "pages": [
            {
                "pageNumber": 1,
                "dimension": {"width": 8.5, "height": 11.0, "unit": "INCH"},
                "paragraphs": [
                    {
                        "layout": {
                            "textAnchor": {"textSegments": [{"startIndex": "0", "endIndex": "14"}]},
                            "boundingPoly": {
                                "normalizedVertices": [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}]
                            },
                        }
                    }
                ],
                "blocks": [],
                "tables": [
                    {
                        "headerRows": [
                            {
                                "cells": [
                                    {
                                        "layout": {
                                            "textAnchor": {
                                                "textSegments": [{"startIndex": "15", "endIndex": "25"}]
                                            },
                                            "boundingPoly": {
                                                "normalizedVertices": [{"x": 0.1, "y": 0.2}, {"x": 0.5, "y": 0.25}]
                                            },
                                        }
                                    }
                                ]
                            }
                        ],
                        "bodyRows": [
                            {
                                "cells": [
                                    {
                                        "layout": {
                                            "textAnchor": {
                                                "textSegments": [{"startIndex": "26", "endIndex": "33"}]
                                            },
                                            "boundingPoly": {
                                                "normalizedVertices": [{"x": 0.1, "y": 0.3}, {"x": 0.5, "y": 0.35}]
                                            },
                                        }
                                    },
                                    {
                                        "layout": {
                                            "textAnchor": {
                                                "textSegments": [{"startIndex": "34", "endIndex": "41"}]
                                            },
                                            "boundingPoly": {
                                                "normalizedVertices": [{"x": 0.5, "y": 0.3}, {"x": 0.9, "y": 0.35}]
                                            },
                                        }
                                    },
                                ]
                            }
                        ],
                    }
                ],
            }
        ],
        "entities": [
            {
                "type": "section_annexure",
                "mentionText": "Annexure A – Sample",
                "textAnchor": {"textSegments": [{"startIndex": "42", "endIndex": "64"}]},
                "pageAnchor": {"pageRefs": [{"page": 1}]},
                "fileUri": "gs://rawtenderdata/tid-123/annexure-a.pdf",
            }
        ],
        "revisions": [],
    }

    normalized = normalize_docai_documents(
        [document],
        tender_id="tid-123",
        raw_uris=["gs://rawtenderdata/tid-123/input.pdf"],
        docai_output_uris=["gs://parsedtenderdata/tid-123/docai/output/result-0.json"],
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    assert normalized["tenderId"] == "tid-123"
    assert normalized["source"]["docAiOutput"] == [
        "gs://parsedtenderdata/tid-123/docai/output/result-0.json"
    ]
    assert normalized["document"]["pages"][0]["pageNumber"] == 1
    first_block = normalized["document"]["pages"][0]["blocks"][0]
    assert first_block["text"] == "Section Header"
    headers = normalized["document"]["tables"][0]["headers"]
    assert headers[0]["text"] == "Row Header"
    sections = normalized["document"]["sections"]
    assert sections[0]["title"] == "Annexure A – Sample"
    anchor_id = first_block["anchorId"]
    assert normalized["textIndex"]["anchors"][anchor_id]["startIndex"] == 0
    attachments = normalized["document"]["attachments"]
    assert attachments[0]["name"] == "Annexure A – Sample"
    assert attachments[0]["rawUri"] == "gs://rawtenderdata/tid-123/annexure-a.pdf"
