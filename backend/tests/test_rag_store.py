from datetime import datetime, timezone

from backend.app import schemas
from backend.app.store import TenderStore


def test_rag_ingestion_defaults():
    store = TenderStore()
    session = store.create_session()

    assert session.rag_ingestion.status == schemas.RagIngestionStatus.PENDING
    assert session.rag_ingestion.operation_name is None
    assert session.rag_files == []


def test_update_rag_ingestion_and_rag_files():
    store = TenderStore()
    session = store.create_session()

    store.update_rag_ingestion(
        session.tender_id,
        status=schemas.RagIngestionStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    updated = store.update_rag_ingestion(
        session.tender_id,
        completed_at=datetime.now(timezone.utc),
        last_error=None,
    )

    assert updated.rag_ingestion.status == schemas.RagIngestionStatus.RUNNING
    assert updated.rag_ingestion.started_at is not None
    assert updated.rag_ingestion.completed_at is not None

    rag_file = schemas.RagFile(
        rag_file_name="projects/test/locations/us-east4/ragCorpora/123/ragFiles/456",
        source_uri="gs://bucket/file.pdf",
    )
    updated = store.set_rag_files(session.tender_id, [rag_file])

    assert len(updated.rag_files) == 1
    assert updated.rag_files[0].rag_file_name.endswith("456")
