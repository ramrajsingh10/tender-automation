from __future__ import annotations

import logging
import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from generator import AnnexureArtifactGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GenerateRequest(BaseModel):
    tenderId: str = Field(..., alias="tenderId")
    annexureIds: Optional[List[str]] = Field(default=None, alias="annexureIds")


class ArtifactResponse(BaseModel):
    id: str
    annexureId: str
    googleDocId: str | None = None
    googleDocUrl: str | None = None


class GenerateResponse(BaseModel):
    tenderId: str
    artifacts: List[ArtifactResponse]


def create_app() -> FastAPI:
    parent_folder = os.environ.get("GOOGLE_DRIVE_PARENT_FOLDER_ID")
    generator = AnnexureArtifactGenerator(parent_folder_id=parent_folder)

    app = FastAPI(
        title="Annexure Artifact Builder",
        description="Generates Google Docs artifacts for approved annexures.",
        version="0.1.0",
    )

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/generate", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
    def generate(request: GenerateRequest) -> GenerateResponse:
        tender_id = request.tenderId
        try:
            artifacts = generator.generate(tender_id, request.annexureIds)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        responses = [ArtifactResponse(**artifact) for artifact in artifacts]
        return GenerateResponse(tenderId=tender_id, artifacts=responses)

    return app


app = create_app()
