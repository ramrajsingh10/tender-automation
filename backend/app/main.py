from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import dashboard, tenders, uploads
from .settings import api_settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Tender Automation Backend",
        version="0.1.0",
        description=(
            "Backend services for tender upload, parsing orchestration, "
            "and validation workflows."
        ),
    )

    @app.get("/health", tags=["meta"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(api_settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(tenders.router)
    app.include_router(uploads.router)
    app.include_router(dashboard.router)

    return app


app = create_app()
