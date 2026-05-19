from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.observability import (
    init_observability,
    request_id_ctx,
)
from app.indexer.qdrant_client import ensure_collection


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_observability()
    settings = get_settings()
    settings.assert_production_secrets()  # v1.4: refuse to start with default JWT in prod
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


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject / propagate `X-Request-ID` and bind it to the request-scoped contextvar."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        token = request_id_ctx.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = rid
        return response


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="TaskRAG API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    # slowapi rate limiter — best-effort, no-op if dep missing
    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware
        from slowapi.util import get_remote_address

        limiter = Limiter(
            key_func=get_remote_address,
            default_limits=[settings.rate_limit_default],
        )
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(SlowAPIMiddleware)
    except ImportError:
        pass

    register_exception_handlers(app)
    app.include_router(api_router)

    # Prometheus instrumentation — optional, only when dep installed.
    try:
        import os as _os

        from fastapi import Response
        from prometheus_fastapi_instrumentator import Instrumentator

        instrumentator = Instrumentator(
            excluded_handlers=["/metrics", "/health", "/healthz"],
        )
        instrumentator.instrument(app)

        if _os.getenv("PROMETHEUS_MULTIPROC_DIR"):
            # In multiproc mode we cannot use the default Instrumentator.expose:
            # metrics live in shared files written by every process (incl. workers).
            from prometheus_client import (
                CONTENT_TYPE_LATEST,
                CollectorRegistry,
                generate_latest,
                multiprocess,
            )

            @app.get("/metrics", include_in_schema=False)
            def metrics_multiproc() -> Response:
                registry = CollectorRegistry()
                multiprocess.MultiProcessCollector(registry)
                data = generate_latest(registry)
                return Response(content=data, media_type=CONTENT_TYPE_LATEST)
        else:
            instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)
    except ImportError:
        pass

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
