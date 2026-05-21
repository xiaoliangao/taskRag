"""Query Router (Wave-3 Pkg-QR).

Routes each question to a retrieval strategy of appropriate depth so we
don't burn full multi-query + CRAG + GraphRAG on every "what is RAG?"
lookup. Inspired by Adaptive RAG / LangGraph router patterns.

Four routes, ordered roughly by retrieval cost:

- **factual**: single-shot lookup ("what is X", "in Section 3 what method
  is used"). One query, no rewrite, no graph expansion. ~3x faster.
- **comparison**: "X vs Y", "differ between A and B". 2 query variants,
  graph expansion ON (find the connecting concepts).
- **synthesis**: open-ended overview ("summarise the field's view on Y").
  3 query variants, graph expansion ON, CRAG retry ON. (current default)
- **multi_step**: requires reasoning chains. Same retrieval as synthesis;
  the Agent endpoint can be invoked separately if needed.

When the classifier fails or is unsure we fall back to **synthesis** —
correctness over speed. Errors never block QA.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Literal

from app.core.config import get_settings
from app.rag.llm_client import get_llm_client
from app.services.json_llm import safe_parse_json_object, truncate_for_llm

log = logging.getLogger(__name__)

QueryRoute = Literal["factual", "comparison", "synthesis", "multi_step"]

VALID_ROUTES: tuple[QueryRoute, ...] = ("factual", "comparison", "synthesis", "multi_step")
DEFAULT_ROUTE: QueryRoute = "synthesis"

_CACHE_TTL = 7 * 86_400  # routes are deterministic for a given question


_SYSTEM = """你是一个学术问答路由助手。给定用户在论文 RAG 系统里的问题,
将其分类到下面 4 类之一,选择最匹配的:

- factual: 简单事实查询。如 "什么是 RAG", "Section 3 用了什么方法", "几页",
  "X 这篇论文的作者是谁"
- comparison: 比较或对照两个或更多对象。如 "X 与 Y 的差异", "X vs Y",
  "compare A and B 的优劣", "哪个更好"
- synthesis: 开放综合性问题。如 "请综述领域 X 的现状", "近期对 Y 的看法",
  "这个方向有什么趋势"
- multi_step: 需要多步推理 / 分解。如 "先 X 再 Y", "推理为什么...",
  "show me the reasoning behind X"

输出 JSON: {"route": "factual|comparison|synthesis|multi_step"}
- 严格 JSON, 不要 markdown 围栏, 不要解释
- 不确定时倾向 "synthesis"(覆盖度最广)
"""


def _cache_key(question: str) -> str:
    digest = hashlib.md5(question.encode("utf-8")).hexdigest()
    return f"qroute:v1:{digest}"


def _redis_client():
    try:
        import redis

        return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    except Exception:  # pragma: no cover
        return None


def classify_query(question: str) -> QueryRoute:
    """Return the route for `question`. Cached in Redis for 7 days because
    routes are deterministic; the same question always gets the same route."""
    q = (question or "").strip()
    if not q:
        return DEFAULT_ROUTE

    cli = _redis_client()
    key = _cache_key(q)
    if cli is not None:
        try:
            hit = cli.get(key)
            if hit in VALID_ROUTES:
                return hit  # type: ignore[return-value]
        except Exception:
            pass

    try:
        raw = get_llm_client().complete(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": truncate_for_llm(q, 800)},
            ],
            temperature=0.0,
            max_tokens=40,
            feature="query_router",
        )
    except Exception as exc:
        log.warning("query_router LLM failed: %s — using default", exc)
        return DEFAULT_ROUTE

    data = safe_parse_json_object(raw, fallback={})
    candidate = (data.get("route") or "").lower().strip()
    route: QueryRoute = candidate if candidate in VALID_ROUTES else DEFAULT_ROUTE  # type: ignore[assignment]

    if cli is not None:
        try:
            cli.setex(key, _CACHE_TTL, route)
        except Exception:
            pass
    return route


# Retrieval depth knobs by route. Other modules read these so the router
# stays a single source of truth.
ROUTE_CONFIG: dict[QueryRoute, dict] = {
    "factual": {
        # One direct query, no rewrite. Skip CRAG retry (high-confidence
        # lookup; if not found, rewriting won't help). Skip GraphRAG too.
        "variants": 1,
        "crag": False,
        "graphrag": False,
    },
    "comparison": {
        "variants": 2,
        "crag": True,
        "graphrag": True,
    },
    "synthesis": {
        "variants": 3,
        "crag": True,
        "graphrag": True,
    },
    "multi_step": {
        # Same as synthesis on the retrieval side. The user can also hit the
        # /agent endpoint for true multi-step reasoning; this branch just
        # ensures the chat path doesn't truncate context.
        "variants": 3,
        "crag": True,
        "graphrag": True,
    },
}


def config_for(route: QueryRoute) -> dict:
    return ROUTE_CONFIG.get(route, ROUTE_CONFIG[DEFAULT_ROUTE])


__all__ = ["classify_query", "config_for", "QueryRoute", "DEFAULT_ROUTE"]
