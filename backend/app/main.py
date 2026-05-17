from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.indexer.qdrant_client import ensure_collection


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    settings.ensure_storage_dirs()
    try:
        ensure_collection()
    except Exception as exc:
        # Don't crash on startup if Qdrant is briefly unavailable;
        # workers will retry on first ingest.
        import logging

        logging.getLogger(__name__).warning(
            "Failed to ensure Qdrant collection on startup: %s", exc
        )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="TaskRAG API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_base_url, "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
