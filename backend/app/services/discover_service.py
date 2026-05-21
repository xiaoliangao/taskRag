"""Topic-less paper discovery.

Same multi-source fallback chain as `picker_service`, but driven by an ad-hoc
user query rather than a saved topic's keywords. Results are cached in Redis
keyed by (sorted sources, sorted keywords, limit) — independent of any topic.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta

from app.collectors.base import RawDocument, dedupe_raw_docs
from app.core.config import get_settings
from app.rag.reranker import get_reranker
from app.services.picker_service import _redis_client, _search_preview_for_source

log = logging.getLogger(__name__)

_DEFAULT_SOURCES = ["arxiv", "openalex", "semantic_scholar"]
_RERANK_SCORE_FLOOR = 0.18  # results below this against the user query are dropped


def _discover_cache_key(sources: list[str], keywords: list[str], limit: int) -> str:
    payload = json.dumps(
        {"s": sorted(sources), "k": sorted(keywords), "n": limit},
        ensure_ascii=False,
    )
    digest = hashlib.md5(payload.encode("utf-8")).hexdigest()
    return f"discover:v1:{digest}"


def _rerank_and_filter(
    user_query: str, docs: list[RawDocument]
) -> list[RawDocument]:
    """Score (title + abstract) against the user's original query with the local
    bge-reranker, sort desc, drop the long tail below the score floor.

    Falls back to the input order on reranker failure — never hides results
    just because the local model is unavailable. The floor (`_RERANK_SCORE_FLOOR`)
    is intentionally lenient: when the upstream API returned all-noise we'd
    rather show a thin list than an empty one.
    """
    if not docs:
        return docs
    rer = get_reranker()
    passages = [(d.title or "") + "\n" + (d.abstract or "") for d in docs]
    scores = rer.rerank(user_query, passages)
    if scores is None:
        return docs
    paired = list(zip(docs, scores, strict=True))
    paired.sort(key=lambda p: p[1], reverse=True)
    kept = [d for d, s in paired if s >= _RERANK_SCORE_FLOOR]
    # If the floor cut everything, surface the top 3 regardless so the user
    # at least sees something instead of an empty state.
    if not kept and paired:
        kept = [d for d, _ in paired[:3]]
    # Stash score on metadata for the UI badge.
    for (d, s) in paired:
        if d in kept:
            d.metadata["rerank_score"] = round(float(s), 3)
    return kept


def discover_search(
    *,
    keywords: list[str],
    sources: list[str] | None,
    limit: int,
    days: int | None = None,
    user_query: str | None = None,
) -> tuple[list[RawDocument], list[str]]:
    """Run the picker fallback chain without any topic context.

    `keywords` should be the LLM-expanded list (CJK→English) — these are what
    the collectors actually use as their search filter. `user_query` is the
    untouched original input, used as the reranker query so the rerank match
    reflects the user's intent rather than the expanded terms (which are
    optimised for recall, not for matching the original).

    Returns (deduped+reranked docs, rate_limited_sources).
    """
    settings = get_settings()
    src_list = [s for s in (sources or _DEFAULT_SOURCES) if s in _DEFAULT_SOURCES]
    if not src_list:
        src_list = list(_DEFAULT_SOURCES)
    kws = [k.strip() for k in keywords if k and k.strip()]
    if not kws:
        return [], []

    cli = _redis_client()
    cache_key = _discover_cache_key(src_list, kws, limit)
    if cli is not None:
        try:
            hit = cli.get(cache_key)
            if hit:
                blob = json.loads(hit)
                docs = [RawDocument.model_validate(d) for d in blob.get("docs", [])]
                # Rerank still runs on cache hit — query may differ from cache
                # key (cache key is the keyword-set; rerank uses original query).
                if user_query:
                    docs = _rerank_and_filter(user_query, docs)
                return docs, list(blob.get("rate_limited", []))
        except Exception as exc:
            log.warning("discover cache read failed: %s", exc)

    since = datetime.now(tz=UTC) - timedelta(days=days or settings.backfill_days)
    all_docs: list[RawDocument] = []
    rate_limited: list[str] = []
    for src in src_list:
        docs, rl = _search_preview_for_source(
            primary_source=src,
            keywords=kws,
            since=since,
            max_results=limit,
            timeout_s=settings.manual_preview_source_timeout_s,
        )
        all_docs.extend(docs)
        if rl and not docs:
            rate_limited.append(src)
    deduped = dedupe_raw_docs(all_docs)[:limit]

    if cli is not None:
        try:
            cli.setex(
                cache_key,
                settings.manual_preview_cache_ttl_s,
                json.dumps(
                    {
                        "docs": [d.model_dump(mode="json") for d in deduped],
                        "rate_limited": rate_limited,
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            log.warning("discover cache write failed: %s", exc)

    if user_query:
        deduped = _rerank_and_filter(user_query, deduped)
    return deduped, rate_limited
