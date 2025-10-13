from __future__ import annotations

from fastapi import FastAPI, status


def create_app() -> FastAPI:
    app = FastAPI(
        title="QA Loop Placeholder",
        description="Acknowledges pipeline QA tasks. Replace with real quality gates.",
        version="0.1.0",
    )

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/qa", status_code=status.HTTP_200_OK)
    async def qa(payload: dict) -> dict:
        return {"status": "ack", "payload": payload}

    return app


app = create_app()
