from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    auth,
    briefings,
    documents,
    notifications,
    qa,
    settings_route,
    tasks,
    topics,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(topics.router, prefix="/topics", tags=["topics"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(briefings.router, tags=["briefings"])
api_router.include_router(qa.router, tags=["qa"])
api_router.include_router(tasks.router, tags=["tasks"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(settings_route.router, prefix="/settings", tags=["settings"])

from app.api.routes import admin as _admin_route  # noqa: E402

api_router.include_router(_admin_route.router, prefix="/admin", tags=["admin"])

from app.api.routes import discover as _discover_route  # noqa: E402

api_router.include_router(_discover_route.router, prefix="/discover", tags=["discover"])

from app.api.routes import annotations as _annotations_route  # noqa: E402

api_router.include_router(_annotations_route.router, tags=["annotations"])

from app.api.routes import translation as _translation_route  # noqa: E402

api_router.include_router(_translation_route.router, prefix="/translate", tags=["translate"])

from app.api.routes import admin_eval as _admin_eval_route  # noqa: E402

api_router.include_router(_admin_eval_route.router, prefix="/admin/eval", tags=["admin-eval"])

# v1.1+ intelligence layer (added as each module is implemented)
try:
    from app.api.routes import pulses  # noqa: F401

    api_router.include_router(pulses.router, tags=["pulses"])
except ImportError:
    pass

try:
    from app.api.routes import reading_paths  # noqa: F401

    api_router.include_router(reading_paths.router, tags=["reading-paths"])
except ImportError:
    pass

try:
    from app.api.routes import insights  # noqa: F401

    api_router.include_router(insights.router, tags=["insights"])
except ImportError:
    pass

try:
    from app.api.routes import notes  # noqa: F401

    api_router.include_router(notes.router, tags=["notes"])
except ImportError:
    pass

try:
    from app.api.routes import trends  # noqa: F401

    api_router.include_router(trends.router, tags=["trends"])
except ImportError:
    pass

try:
    from app.api.routes import conflicts  # noqa: F401

    api_router.include_router(conflicts.router, tags=["conflicts"])
except ImportError:
    pass

try:
    from app.api.routes import signals  # noqa: F401

    api_router.include_router(signals.router, tags=["signals"])
except ImportError:
    pass

try:
    from app.api.routes import hypotheses  # noqa: F401

    api_router.include_router(hypotheses.router, tags=["hypotheses"])
except ImportError:
    pass

try:
    from app.api.routes import comparisons  # noqa: F401

    api_router.include_router(comparisons.router, tags=["comparisons"])
except ImportError:
    pass

try:
    from app.api.routes import writing  # noqa: F401

    api_router.include_router(writing.router, tags=["writing"])
except ImportError:
    pass

try:
    from app.api.routes import graph  # noqa: F401

    api_router.include_router(graph.router, tags=["graph"])
except ImportError:
    pass

try:
    from app.api.routes import glossary  # noqa: F401

    api_router.include_router(glossary.router, tags=["glossary"])
except ImportError:
    pass

try:
    from app.api.routes import exports  # noqa: F401

    api_router.include_router(exports.router, tags=["exports"])
except ImportError:
    pass

try:
    from app.api.routes import qa_cross  # noqa: F401

    api_router.include_router(qa_cross.router, tags=["qa-cross"])
except ImportError:
    pass

try:
    from app.api.routes import methods  # noqa: F401

    api_router.include_router(methods.router, tags=["methods"])
except ImportError:
    pass

try:
    from app.api.routes import agent  # noqa: F401

    api_router.include_router(agent.router, tags=["agent"])
except ImportError:
    pass

try:
    from app.api.routes import recommendations as _reco_route  # noqa: F401

    api_router.include_router(_reco_route.router, tags=["recommendations"])
except ImportError:
    pass
